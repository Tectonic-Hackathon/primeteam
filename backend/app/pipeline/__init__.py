from ..embeddings import backend as embed_backend
from ..taxonomy import TOPIC_LABELS, COUNTRY_NAMES
from . import context, planner, retrieval, trust, conflicts, consolidate
from .experts import Reputation


def ask(conn, question: str, user: dict | None = None) -> dict:
    rep = Reputation(conn)
    people = rep.people
    with conn.cursor() as cur:
        cur.execute("SELECT id, title, updated_at, supersedes_id FROM documents WHERE supersedes_id IS NOT NULL")
        superseded_by = {r["supersedes_id"]: r for r in cur.fetchall()}

    ctx = context.resolve(question, user)
    subs = planner.plan(question, ctx)
    per_sub = []
    for sub in subs:
        cands = retrieval.retrieve(conn, sub, ctx)
        ids = [c["chunk_id"] for c in cands]
        embeddings = {}
        if ids:
            with conn.cursor() as cur:
                cur.execute("SELECT id, embedding FROM chunks WHERE id = ANY(%s)", (ids,))
                embeddings = {r["id"]: list(r["embedding"]) for r in cur.fetchall()}
        for c in cands:
            c["trust"] = trust.score(c, ctx, people, superseded_by, rep)
        per_sub.append(conflicts.analyse(cands, sub, embeddings))

    result = consolidate.consolidate(question, ctx, subs, per_sub, rep.find, people)
    # experts who can confirm the answer overall
    topics = ctx["topics"] or [t for s in subs for t in s["topics"]]
    result["experts"] = rep.find(topics, ctx.get("country"), limit=3) if topics else []
    result["graph"] = build_graph(conn, result, people, topics)
    result["pipeline"] = {
        "embedding_backend": embed_backend(),
        "steps": [
            {"name": "Resolve context", "detail": f"country={ctx['country'] or 'any'}, client={ctx['client'] or 'none'}, team={ctx['team'] or 'any'}, intent={ctx['intent']}"},
            {"name": "Plan", "detail": f"{len(subs)} sub-question(s), {sum(len(s['rewrites']) for s in subs)} rewrites"},
            {"name": "Hybrid retrieval", "detail": "pgvector cosine + Postgres full-text, reciprocal rank fusion"},
            {"name": "Trust scoring", "detail": "freshness, owner, scope, authority, channel, supersession"},
            {"name": "Conflict detection", "detail": f"{result['review_count']} item(s) sent for review"},
            {"name": "Consolidate", "detail": f"{len(result['evidence'])} evidence passages cited"},
        ],
    }
    return result


def build_graph(conn, result: dict, people: dict, topics: list[str]) -> dict:
    """Tripartite graph for the answer: people – documents – topics, with the relation on every link."""
    docs: dict[str, dict] = {}
    def add_doc(card, role):
        d = docs.setdefault(card["document_id"], {"id": card["document_id"], "title": card["title"], "doc_type": card["doc_type"],
                                                   "country": card["country_name"], "updated_at": card["updated_at"], "roles": set(), "evidence_id": None})
        d["roles"].add(role)
        if role == "evidence":
            d["evidence_id"] = card["id"]
    for e in result["evidence"]:
        add_doc(e, "evidence")
    for c in result["review"]["conflicts"]:
        add_doc(c["rejected"], "conflict")
    for d in result["review"]["duplicates"]:
        add_doc(d["duplicate"], "duplicate")
    for o in result["review"]["outdated"]:
        add_doc(o["item"], "outdated")
    for o in result["review"]["out_of_scope"]:
        add_doc(o["item"], "out_of_scope")
    if not docs:
        return {"people": [], "documents": [], "topics": [], "links": []}
    doc_ids = list(docs)
    with conn.cursor() as cur:
        cur.execute("SELECT id, topics FROM documents WHERE id = ANY(%s)", (doc_ids,))
        doc_topics = {r["id"]: r["topics"] for r in cur.fetchall()}
        cur.execute("SELECT src, rel, dst, at FROM edges WHERE dst = ANY(%s) AND src LIKE 'person:%%'", ([f"doc:{d}" for d in doc_ids],))
        person_edges = cur.fetchall()
        expert_ids = [e["id"] for e in result["experts"]] + [e["id"] for sec in result["sections"] for e in sec["experts"]]
        cur.execute("SELECT src, rel, dst, at FROM edges WHERE dst = ANY(%s) AND src = ANY(%s)",
                    ([f"topic:{t}" for t in topics], [f"person:{p}" for p in set(expert_ids)]))
        topic_edges = cur.fetchall()
    links, persons, topic_set = [], {}, set(topics)
    for e in person_edges:
        pid = e["src"].split(":", 1)[1]
        if pid not in people:
            continue
        persons[pid] = people[pid]
        links.append({"from": f"person:{pid}", "to": e["dst"], "rel": e["rel"], "at": e["at"].isoformat()})
    for e in topic_edges:
        pid = e["src"].split(":", 1)[1]
        persons[pid] = people[pid]
        links.append({"from": e["src"], "to": e["dst"], "rel": e["rel"], "at": e["at"].isoformat()})
    for did, ts in doc_topics.items():
        for t in ts or []:
            if t in topic_set or t in topics:
                links.append({"from": f"doc:{did}", "to": f"topic:{t}", "rel": "about", "at": None})
                topic_set.add(t)
    expert_scores = {e["id"]: e["score"] for e in result["experts"]}
    for sec in result["sections"]:
        for e in sec["experts"]:
            expert_scores.setdefault(e["id"], e["score"])
    return {
        "people": [{"id": pid, "name": p["name"], "role": p["role"], "active": p["active"], "score": expert_scores.get(pid),
                    "initials": "".join(w[0] for w in p["name"].split()[:2]).upper()} for pid, p in persons.items()],
        "documents": [{**d, "roles": sorted(d["roles"])} for d in docs.values()],
        "topics": [{"id": t, "label": TOPIC_LABELS.get(t, t)} for t in topic_set],
        "links": links,
    }
