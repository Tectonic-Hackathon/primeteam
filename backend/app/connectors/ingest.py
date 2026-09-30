"""Turn KnowledgeUnits into documents, chunks, embeddings and graph edges. Idempotent per (connector, external_id)."""
import hashlib
import re
from ..embeddings import embed
from ..pipeline.context import detect_topics, resolve
from ..pipeline.conflicts import facts
from ..taxonomy import TEAMS
from .base import KnowledgeUnit


def h(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


_VERSION_NOISE = re.compile(r"\s*[\(\[]?(?:v\.?\s*\d+(?:\.\d+)?|version\s*\d+|\b(?:19|20)\d{2}\b|copy|final|draft)[\)\]]?\s*", re.I)


def title_stem(title: str) -> str:
    """'Belgium – Notice Periods Policy (v2, 2025)' → 'belgium notice periods policy'"""
    t = _VERSION_NOISE.sub(" ", title.lower())
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(w for w in t.split() if w not in ("v", "version"))


def change_summary(old_body: str, new_body: str) -> str:
    """Section-level fact diff in plain words, e.g. 'Entitlement: 30 days → 60 days'."""
    def sections(body):
        out, cur, buf = {}, None, []
        for line in body.split("\n"):
            if line.startswith("## "):
                if cur:
                    out[cur] = " ".join(buf)
                cur, buf = line[3:], []
            elif cur:
                buf.append(line)
        if cur:
            out[cur] = " ".join(buf)
        return out
    a, b = sections(old_body), sections(new_body)
    parts = []
    for sec in b:
        if sec not in a:
            parts.append(f"{sec}: added")
            continue
        if a[sec] == b[sec]:
            continue
        fa, fb = facts(a[sec]), facts(b[sec])
        gone, new = [f for f in fa if f not in fb], [f for f in fb if f not in fa]
        if gone or new:
            parts.append(f"{sec}: {', '.join(gone) or '—'} → {', '.join(new) or '—'}")
        else:
            parts.append(f"{sec}: wording changed")
    for sec in a:
        if sec not in b:
            parts.append(f"{sec}: removed")
    return "; ".join(parts) or "content changed"


def link_supersession(cur, doc_id: str, title: str, country, updated_at) -> str | None:
    """A newer document with the same title stem and country supersedes the older one, and vice versa."""
    stem = title_stem(title)
    cur.execute("SELECT id, title, country, updated_at, supersedes_id FROM documents WHERE id <> %s AND status <> 'retracted' AND (country IS NOT DISTINCT FROM %s)", (doc_id, country))
    for r in cur.fetchall():
        if title_stem(r["title"]) != stem:
            continue
        if str(r["updated_at"]) < str(updated_at):
            cur.execute("UPDATE documents SET supersedes_id = %s WHERE id = %s AND supersedes_id IS NULL", (r["id"], doc_id))
            return r["id"]
        else:
            cur.execute("UPDATE documents SET supersedes_id = %s WHERE id = %s AND supersedes_id IS NULL", (doc_id, r["id"]))
    return None


def _doc_id(prefix: str, external_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", external_id).strip("-")[:40]
    return f"{prefix}-{slug}"


def _body(unit: KnowledgeUnit):
    lines = [unit.title, ""]
    chunks = []
    for heading, sents in unit.sections:
        if not sents:
            continue
        lines.append(f"## {heading}")
        start = len(lines) + 1
        lines.extend(sents)
        chunks.append((heading, start, len(lines), " ".join(sents)))
        lines.append("")
    return "\n".join(lines), chunks


def _guess_team(text: str) -> str | None:
    t = text.lower()
    best, hits = None, 0
    for name, kws in TEAMS.items():
        n = sum(1 for k in kws if k in t)
        if n > hits:
            best, hits = name, n
    return best


def upsert(conn, connector, units: list[KnowledgeUnit], since=None, trigger="manual", full=False) -> dict:
    """Idempotent ingest with change detection:
    - unchanged content hash → touch last_seen_at only (no re-embedding)
    - changed → new document_versions row with a fact-level change summary, an 'edited' edge for the modifier,
      re-chunk and re-embed only the sections whose text changed
    - new document with the same title stem as an older one → supersession link
    - full sync: documents from this source not seen anymore → archived (tombstone)"""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO sync_runs (connector, mode, since, trigger) VALUES (%s, %s, %s, %s) RETURNING id", (connector.name, connector.mode, since, trigger))
        run_id = cur.fetchone()["id"]
        cur.execute("SELECT id, email FROM people WHERE email IS NOT NULL")
        by_email = {r["email"].lower(): r["id"] for r in cur.fetchall()}
        inserted = updated = unchanged = archived = 0
        seen_ids = []
        for u in units:
            if not u.sections:
                continue
            doc_id = _doc_id(connector.id_prefix, u.external_id)
            seen_ids.append(doc_id)
            body, chunks = _body(u)
            new_hash = h(body)
            cur.execute("SELECT content_hash, body, updated_at FROM documents WHERE id = %s", (doc_id,))
            existing = cur.fetchone()
            if existing and existing["content_hash"] == new_hash:
                cur.execute("UPDATE documents SET last_seen_at = now() WHERE id = %s", (doc_id,))
                unchanged += 1
                continue
            full_text = f"{u.title} {body}"
            topics = u.topics or detect_topics(full_text)
            ctx = resolve(full_text)
            country = u.country or ctx["country"]
            client = u.client or ctx["client"]
            owner = by_email.get((u.owner_email or "").lower())
            author = by_email.get((u.author_email or "").lower()) or owner
            cur.execute("""INSERT INTO documents (id, title, doc_type, source_system, country, client, team, product, topics, owner_id, author_id,
                                                  created_at, updated_at, version, supersedes_id, location, url, body, status, content_hash, last_seen_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, 'active', %s, now())
                           ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, doc_type = EXCLUDED.doc_type, country = EXCLUDED.country,
                             client = EXCLUDED.client, team = EXCLUDED.team, topics = EXCLUDED.topics, owner_id = EXCLUDED.owner_id,
                             author_id = EXCLUDED.author_id, updated_at = EXCLUDED.updated_at, version = EXCLUDED.version,
                             location = EXCLUDED.location, url = EXCLUDED.url, body = EXCLUDED.body, content_hash = EXCLUDED.content_hash,
                             last_seen_at = now(), status = CASE WHEN documents.status IN ('archived', 'needs_update') THEN 'active' ELSE documents.status END""",
                        (doc_id, u.title, u.doc_type, connector.source_system, country, client, u.team or _guess_team(full_text), u.product, topics,
                         owner, author, u.created_at or u.updated_at, u.updated_at, u.version, u.location, u.url, body, new_hash))
            # version history
            cur.execute("SELECT coalesce(max(version_no), 0) AS n FROM document_versions WHERE document_id = %s", (doc_id,))
            vno = cur.fetchone()["n"] + 1
            summary = change_summary(existing["body"], body) if existing else "first version indexed"
            cur.execute("INSERT INTO document_versions (document_id, version_no, body, content_hash, changed_by, changed_at, change_summary) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (doc_id, vno, body, new_hash, owner, u.updated_at, summary))
            if existing and owner:
                cur.execute("INSERT INTO edges (src, rel, dst, at, note) VALUES (%s, 'edited', %s, %s, %s)", (f"person:{owner}", f"doc:{doc_id}", u.updated_at, summary[:120]))
                cur.execute("UPDATE tasks SET done = TRUE WHERE document_id = %s AND kind IN ('request_update', 'confirm_valid') AND NOT done", (doc_id,))
            # chunks: keep embeddings of unchanged sections
            cur.execute("SELECT content_hash, embedding FROM chunks WHERE document_id = %s", (doc_id,))
            old_emb = {r["content_hash"]: r["embedding"] for r in cur.fetchall() if r["content_hash"]}
            cur.execute("DELETE FROM chunks WHERE document_id = %s", (doc_id,))
            for heading, start, end, text in chunks:
                ch = h(f"{u.title}. {heading}. {text}")
                emb = old_emb.get(ch)
                if emb is None:
                    emb = embed(f"{u.title}. {heading}. {text}")
                cur.execute("INSERT INTO chunks (document_id, section, line_start, line_end, text, topics, embedding, content_hash) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                            (doc_id, heading, start, end, text, topics, emb, ch))
            # graph edges
            cur.execute("DELETE FROM edges WHERE dst = %s AND rel IN ('owns', 'authored', 'attended')", (f"doc:{doc_id}",))
            if owner:
                cur.execute("INSERT INTO edges (src, rel, dst, at) VALUES (%s, 'owns', %s, %s)", (f"person:{owner}", f"doc:{doc_id}", u.updated_at))
            if author:
                cur.execute("INSERT INTO edges (src, rel, dst, at) VALUES (%s, 'authored', %s, %s)", (f"person:{author}", f"doc:{doc_id}", u.created_at or u.updated_at))
            for em in u.attendee_emails:
                pid = by_email.get(em.lower())
                if pid and pid != owner:
                    cur.execute("INSERT INTO edges (src, rel, dst, at) VALUES (%s, 'attended', %s, %s)", (f"person:{pid}", f"doc:{doc_id}", u.updated_at))
            link_supersession(cur, doc_id, u.title, country, u.updated_at)
            if existing:
                updated += 1
            else:
                inserted += 1
        if full and seen_ids:
            cur.execute("UPDATE documents SET status = 'archived' WHERE source_system = %s AND id LIKE %s AND status = 'active' AND NOT (id = ANY(%s)) RETURNING id",
                        (connector.source_system, f"{connector.id_prefix}-%", seen_ids))
            archived = len(cur.fetchall())
        cur.execute("UPDATE sync_runs SET fetched = %s, inserted = %s, updated = %s, unchanged = %s, archived = %s, finished_at = now() WHERE id = %s",
                    (len(units), inserted, updated, unchanged, archived, run_id))
    return {"connector": connector.name, "label": connector.label, "mode": connector.mode, "fetched": len(units), "inserted": inserted, "updated": updated, "unchanged": unchanged, "archived": archived}
