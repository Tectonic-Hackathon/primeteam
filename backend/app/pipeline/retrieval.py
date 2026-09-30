"""Step 3: hybrid retrieval (pgvector cosine + Postgres full text) fused with reciprocal rank fusion."""
import re
from ..embeddings import embed
from ..taxonomy import STOPWORDS, INTENT_DOC_TYPES

_TOKEN = re.compile(r"[a-z0-9€£%]+")

SQL = """
WITH q AS (SELECT %(vec)s::vector AS v, websearch_to_tsquery('english', %(text)s) AS tq),
vec AS (SELECT id FROM chunks ORDER BY embedding <=> (SELECT v FROM q) LIMIT %(k)s)
SELECT c.id AS chunk_id, c.document_id, c.section, c.line_start, c.line_end, c.text, c.topics AS chunk_topics,
       1 - (c.embedding <=> q.v) AS sim,
       ts_rank_cd(c.tsv, q.tq) AS fts,
       d.title, d.doc_type, d.source_system, d.country, d.client, d.team, d.product, d.topics AS doc_topics,
       d.owner_id, d.author_id, d.created_at, d.updated_at, d.version, d.supersedes_id, d.location, d.url, d.status, d.validated_at
FROM chunks c JOIN documents d ON d.id = c.document_id, q
WHERE d.status IN ('active', 'needs_update') AND (c.tsv @@ q.tq OR c.id IN (SELECT id FROM vec))
"""


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS and len(t) > 2}


def _lexical(query: str, chunk: dict) -> float:
    qt = _tokens(query)
    if not qt:
        return 0.0
    ct = _tokens(chunk["section"] + " " + chunk["text"] + " " + chunk["title"])
    return len(qt & ct) / len(qt)


def retrieve(conn, sub: dict, ctx: dict, k: int = 15) -> list[dict]:
    queries = [sub["text"]] + sub["rewrites"]
    pool: dict[int, dict] = {}
    rrf: dict[int, float] = {}
    for qi, qtext in enumerate(queries):
        weight = 1.0 if qi == 0 else 0.6
        vec = embed(qtext)
        with conn.cursor() as cur:
            cur.execute(SQL, {"vec": vec, "text": qtext, "k": k})
            rows = cur.fetchall()
        by_sim = sorted(rows, key=lambda r: -r["sim"])
        by_fts = sorted(rows, key=lambda r: -r["fts"])
        for rank, r in enumerate(by_sim):
            rrf[r["chunk_id"]] = rrf.get(r["chunk_id"], 0) + weight / (20 + rank)
        for rank, r in enumerate(by_fts):
            if r["fts"] > 0:
                rrf[r["chunk_id"]] = rrf.get(r["chunk_id"], 0) + weight / (20 + rank)
        for r in rows:
            cur_best = pool.get(r["chunk_id"])
            if cur_best is None or r["sim"] > cur_best["sim"]:
                pool[r["chunk_id"]] = dict(r)
    out = []
    for cid, row in pool.items():
        lex = _lexical(sub["text"], row)
        topic_hit = bool(set(sub["topics"]) & set(row["chunk_topics"] or []))
        sim = max(0.0, float(row["sim"]))
        # nomic cosine for related text tends to sit around 0.6-0.85; rescale to 0..1
        sim_n = min(1.0, max(0.0, (sim - 0.45) / 0.4))
        relevance = 0.45 * sim_n + 0.35 * lex + (0.2 if topic_hit else 0.0)
        # intent boosts: a 'what did we decide' question prefers meeting decisions, 'how do I' prefers procedures
        intent = ctx.get("intent", "rule")
        if row["doc_type"] in INTENT_DOC_TYPES.get(intent, []):
            relevance += 0.05
        if intent == "decision" and "decision" in row["section"].lower():
            relevance += 0.15
        if intent == "procedure" and ("step" in row["section"].lower() or row["doc_type"] == "procedure"):
            relevance += 0.05
        relevance = min(1.0, relevance)
        row.update({"lexical": round(lex, 3), "topic_hit": topic_hit, "relevance": round(relevance, 3), "rrf": rrf.get(cid, 0)})
        out.append(row)
    out.sort(key=lambda r: (-r["relevance"], -r["rrf"]))
    return out[:12]
