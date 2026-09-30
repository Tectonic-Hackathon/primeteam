"""Rebuild the database from corpus.py: people, documents, chunks (with embeddings), edges."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import connect, init_schema
from app.embeddings import embed, backend
from seed.corpus import PEOPLE, DOCS, EDGES


def build_body(doc: dict):
    lines = [doc["title"], ""]
    chunks = []
    for heading, sentences in doc["sections"]:
        lines.append(f"## {heading}")
        start = len(lines) + 1
        lines.extend(sentences)
        end = len(lines)
        chunks.append((heading, start, end, " ".join(sentences)))
        lines.append("")
    return "\n".join(lines), chunks


def main():
    conn = connect()
    init_schema(conn)
    print(f"embedding backend: {backend()}")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE tasks, sync_runs, document_versions, edges, chunks, documents, people CASCADE")
        for p in PEOPLE:
            cur.execute("""INSERT INTO people (id, name, role, team, country, seniority_years, email, active)
                           VALUES (%(id)s, %(name)s, %(role)s, %(team)s, %(country)s, %(seniority_years)s, %(email)s, %(active)s)""", p)
        for d in DOCS:
            body, chunks = build_body(d)
            cur.execute("""INSERT INTO documents (id, title, doc_type, source_system, country, client, team, product, topics, owner_id, author_id,
                                                  created_at, updated_at, version, supersedes_id, location, url, body, date_known)
                           VALUES (%(id)s, %(title)s, %(doc_type)s, %(source_system)s, %(country)s, %(client)s, %(team)s, %(product)s, %(topics)s,
                                   %(owner_id)s, %(author_id)s, %(created_at)s, %(updated_at)s, %(version)s, %(supersedes_id)s, %(location)s, %(url)s, %(body)s, %(date_known)s)""",
                        {**{"date_known": True}, **d, "body": body})
            for heading, start, end, text in chunks:
                cur.execute("""INSERT INTO chunks (document_id, section, line_start, line_end, text, topics, embedding)
                               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                            (d["id"], heading, start, end, text, d["topics"], embed(f"{d['title']}. {heading}. {text}")))
            if d["owner_id"]:
                cur.execute("INSERT INTO edges (src, rel, dst, at) VALUES (%s, 'owns', %s, %s)", (f"person:{d['owner_id']}", f"doc:{d['id']}", d["updated_at"]))
            if d["author_id"]:
                cur.execute("INSERT INTO edges (src, rel, dst, at) VALUES (%s, 'authored', %s, %s)", (f"person:{d['author_id']}", f"doc:{d['id']}", d["created_at"]))
            print(f"  indexed {d['id']} ({len(chunks)} chunks)")
        for src, rel, dst, at, note in EDGES:
            cur.execute("INSERT INTO edges (src, rel, dst, at, note) VALUES (%s, %s, %s, %s, %s)", (f"person:{src}", rel, dst, at, note))
        cur.execute("SELECT count(*) AS n FROM chunks")
        print(f"done: {len(PEOPLE)} people, {len(DOCS)} documents, {cur.fetchone()['n']} chunks, edges seeded")


if __name__ == "__main__":
    main()
