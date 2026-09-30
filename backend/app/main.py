import asyncio
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .db import connect, init_schema
from .pipeline import ask
from .embeddings import backend as embed_backend
from .taxonomy import COUNTRY_NAMES, TOPIC_LABELS, CLIENTS
from .embeddings import embed
from .config import TODAY
from . import connectors as conns
from . import freshness

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Grounded – SD Worx knowledge assistant")
conn = connect()
init_schema(conn)


class Ask(BaseModel):
    question: str
    user_id: str | None = None


class ReviewAction(BaseModel):
    action: str                      # retract, archive, request_update, restore, validate
    document_id: str
    question: str | None = None
    actor_id: str | None = None
    note: str | None = None


class Knowledge(BaseModel):
    title: str
    text: str
    doc_type: str = "wiki"          # wiki, meeting, analysis, chat, email
    country: str | None = None
    client: str | None = None
    topics: list[str] = []
    owner_id: str | None = None
    location: str | None = None


SUGGESTIONS = [
    "What is the notice period for a white-collar employee with 5 years of service in Belgium?",
    "How many days of guaranteed salary does a white-collar employee get during sick leave in Belgium?",
    "How many statutory vacation days does a full-time employee get in the Netherlands?",
    "How do I change the meal voucher face value for Colruyt in eBlox, and which provider issues their vouchers after the switch?",
    "What did we decide about holiday pay for Delhaize?",
    "How is the 13th month paid out for Siemens?",
    "What is the notice period for a blue-collar employee in France?",
]


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    with conn.cursor() as cur:
        cur.execute("SELECT (SELECT count(*) FROM documents) AS documents, (SELECT count(*) FROM chunks) AS chunks, (SELECT count(*) FROM people) AS people, (SELECT count(*) FROM edges) AS edges")
        stats = cur.fetchone()
    return {"ok": True, "embedding_backend": embed_backend(), **stats}


@app.get("/api/suggestions")
def suggestions():
    return SUGGESTIONS


@app.get("/api/people")
def people():
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM people ORDER BY name")
        return cur.fetchall()


@app.post("/api/ask")
def api_ask(body: Ask):
    user = None
    if body.user_id:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM people WHERE id = %s", (body.user_id,))
            user = cur.fetchone()
    return ask(conn, body.question, user)


@app.get("/api/meta")
def meta():
    return {"topics": [{"id": k, "label": v} for k, v in TOPIC_LABELS.items()],
            "countries": [{"id": k, "label": v} for k, v in COUNTRY_NAMES.items()],
            "clients": sorted(CLIENTS), "today": TODAY}


@app.post("/api/knowledge")
def add_knowledge(body: Knowledge):
    """Users (or a meeting agent) add knowledge directly. It is indexed immediately and becomes citable."""
    import re
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM documents WHERE id LIKE 'USR-%'")
        doc_id = f"USR-{cur.fetchone()['n'] + 1:04d}"
        sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", body.text.strip()) if x.strip()]
        heading = "Decisions" if body.doc_type == "meeting" else "Note"
        lines = [body.title, "", f"## {heading}", *sentences]
        doc_body = "\n".join(lines)
        source = {"meeting": "Meeting Recorder", "chat": "Teams", "email": "Outlook"}.get(body.doc_type, "Grounded")
        cur.execute("""INSERT INTO documents (id, title, doc_type, source_system, country, client, team, product, topics, owner_id, author_id,
                                              created_at, updated_at, version, location, url, body)
                       VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL, %s, %s, %s, %s, %s, NULL, %s, %s, %s)""",
                    (doc_id, body.title, body.doc_type, source, body.country or None, body.client or None, body.topics,
                     body.owner_id or None, body.owner_id or None, TODAY, TODAY,
                     body.location or f"Grounded › Added by {'user ' + body.owner_id if body.owner_id else 'anonymous'}",
                     f"http://localhost:8000/#doc/{doc_id}", doc_body))
        cur.execute("INSERT INTO chunks (document_id, section, line_start, line_end, text, topics, embedding) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (doc_id, heading, 4, 3 + len(sentences), " ".join(sentences), body.topics, embed(f"{body.title}. {heading}. {' '.join(sentences)}")))
        if body.owner_id:
            cur.execute("INSERT INTO edges (src, rel, dst, at) VALUES (%s, 'owns', %s, %s)", (f"person:{body.owner_id}", f"doc:{doc_id}", TODAY))
            cur.execute("INSERT INTO edges (src, rel, dst, at) VALUES (%s, 'authored', %s, %s)", (f"person:{body.owner_id}", f"doc:{doc_id}", TODAY))
    return {"id": doc_id, "title": body.title}


@app.post("/api/review/action")
def review_action(body: ReviewAction):
    """Fix knowledge from the review tab. Retract/archive hide a document from future answers; request_update keeps it
    but records a task for its owner; restore undoes any of these."""
    status = {"retract": "retracted", "archive": "archived", "request_update": "needs_update", "restore": "active", "validate": "active"}.get(body.action)
    if not status:
        raise HTTPException(400, "unknown action")
    with conn.cursor() as cur:
        cur.execute("SELECT d.id, d.title, d.owner_id, d.author_id, p.name AS owner_name, p.email AS owner_email, a.name AS author_name, a.email AS author_email FROM documents d LEFT JOIN people p ON p.id = d.owner_id LEFT JOIN people a ON a.id = d.author_id WHERE d.id = %s", (body.document_id,))
        d = cur.fetchone()
        if not d:
            raise HTTPException(404, "document not found")
        cur.execute("UPDATE documents SET status = %s WHERE id = %s", (status, body.document_id))
        task = None
        if body.action == "request_update":
            assignee = d["owner_id"] or d["author_id"]
            cur.execute("INSERT INTO tasks (kind, document_id, assignee_id, requested_by, question, note) VALUES ('request_update', %s, %s, %s, %s, %s) RETURNING id",
                        (body.document_id, assignee, body.actor_id, body.question, body.note))
            task = {"id": cur.fetchone()["id"], "assignee": d["owner_name"] or d["author_name"], "email": d["owner_email"] or d["author_email"]}
        if body.action == "restore":
            cur.execute("UPDATE tasks SET done = TRUE WHERE document_id = %s AND done = FALSE", (body.document_id,))
        if body.action == "validate":
            # owner confirms the document is still valid: counts as freshness without an edit
            cur.execute("UPDATE documents SET validated_at = %s WHERE id = %s", (TODAY, body.document_id))
            cur.execute("UPDATE tasks SET done = TRUE WHERE document_id = %s AND kind = 'confirm_valid' AND NOT done", (body.document_id,))
            cur.execute("INSERT INTO edges (src, rel, dst, at, note) VALUES (%s, 'reviewed', %s, %s, 'confirmed still valid')", (f"person:{body.actor_id or d['owner_id']}", f"doc:{body.document_id}", TODAY))
    return {"document_id": body.document_id, "status": status, "title": d["title"], "task": task}


@app.get("/api/tasks")
def tasks():
    with conn.cursor() as cur:
        cur.execute("SELECT t.*, d.title, p.name AS assignee FROM tasks t JOIN documents d ON d.id = t.document_id LEFT JOIN people p ON p.id = t.assignee_id WHERE NOT t.done ORDER BY t.created_at DESC")
        return cur.fetchall()


# ---------------- connectors, ingestion, freshness ----------------
class IngestUnit(BaseModel):
    external_id: str
    title: str
    doc_type: str = "wiki"
    sections: list[list]             # [[heading, [sentences]]]
    updated_at: str
    created_at: str | None = None
    owner_email: str | None = None
    author_email: str | None = None
    attendee_emails: list[str] = []
    country: str | None = None
    client: str | None = None
    team: str | None = None
    topics: list[str] = []
    version: str | None = None
    location: str = ""
    url: str = ""


class IngestDocuments(BaseModel):
    source: str = "API"
    units: list[IngestUnit]


class IngestMeeting(BaseModel):
    id: str
    subject: str
    transcript: str
    createdDateTime: str
    organizer: str | None = None
    attendees: list[str] = []
    client: str | None = None
    country: str | None = None
    location: str = ""
    joinWebUrl: str = ""


class _ApiSource:
    """Connector identity for pushed documents. If the source names a registered connector (e.g. "SharePoint"),
    its id prefix is reused so a pushed change versions the same document a sync would."""
    def __init__(self, source: str):
        match = next((c for c in conns.REGISTRY.values() if source.lower() in (c.name, c.label.lower(), c.source_system.lower())), None)
        self.name = match.name if match else f"push:{source.lower()}"
        self.label = match.label if match else source
        self.source_system = match.source_system if match else source
        self.id_prefix = match.id_prefix if match else "API-" + "".join(ch for ch in source.upper() if ch.isalnum())[:8]
        self.mode = "push"


@app.get("/api/connectors")
def connectors_list():
    return conns.statuses(conn)


@app.post("/api/connectors/{name}/sync")
def connectors_sync(name: str, since: str | None = None, full: bool = False):
    if name not in conns.REGISTRY:
        raise HTTPException(404, "unknown connector")
    return conns.sync(conn, name, since=since, full=full, trigger="manual")


@app.post("/api/ingest/webhook/{name}")
async def connectors_webhook(name: str, request: Request):
    """Change notifications (Graph subscriptions, Jira/Confluence webhooks) land here and trigger a delta sync.
    Graph validates a subscription by sending ?validationToken=..., which must be echoed back as text."""
    token = request.query_params.get("validationToken")
    if token:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(token)
    if name not in conns.REGISTRY:
        raise HTTPException(404, "unknown connector")
    return conns.sync(conn, name, trigger="webhook")


@app.post("/api/ingest/documents")
def ingest_documents(body: IngestDocuments):
    units = [conns.KnowledgeUnit(**{**u.model_dump(), "sections": [(sec[0], list(sec[1])) for sec in u.sections]}) for u in body.units]
    return conns.upsert(conn, _ApiSource(body.source), units, trigger="push")


@app.post("/api/ingest/meeting")
def ingest_meeting(body: IngestMeeting):
    unit = conns.unit_from_transcript(body.id, body.subject, body.transcript, body.createdDateTime, body.organizer, body.attendees,
                                      body.location, body.joinWebUrl, body.client, body.country)
    result = conns.upsert(conn, conns.REGISTRY["meetings"], [unit], trigger="webhook")
    from .connectors.meetings import extract
    return {**result, "extracted": extract(body.transcript)}


@app.get("/api/freshness")
def freshness_overview():
    return {**freshness.overview(conn), "auto_sync_minutes": SYNC_INTERVAL_MINUTES}


@app.post("/api/freshness/sweep")
def freshness_sweep():
    return freshness.sweep(conn)


SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", "30"))


async def _scheduler():
    """Background loop: delta-sync every connector, then run the freshness sweep. Webhooks make this a safety net."""
    await asyncio.sleep(5)
    while True:
        try:
            for name in conns.REGISTRY:
                await asyncio.to_thread(conns.sync, conn, name, None, "schedule", False)
            await asyncio.to_thread(freshness.sweep, conn)
        except Exception as e:  # keep the loop alive
            print("scheduler error:", e)
        await asyncio.sleep(SYNC_INTERVAL_MINUTES * 60)


@app.on_event("startup")
async def _start():
    if SYNC_INTERVAL_MINUTES > 0:
        asyncio.create_task(_scheduler())


@app.get("/favicon.ico")
def favicon():
    return FileResponse(STATIC / "favicon.svg", media_type="image/svg+xml")


@app.get("/api/documents/{doc_id}")
def document(doc_id: str):
    with conn.cursor() as cur:
        cur.execute("""SELECT d.*, o.name AS owner_name, o.role AS owner_role, a.name AS author_name
                       FROM documents d LEFT JOIN people o ON o.id = d.owner_id LEFT JOIN people a ON a.id = d.author_id
                       WHERE d.id = %s""", (doc_id,))
        d = cur.fetchone()
        if not d:
            raise HTTPException(404, "document not found")
        cur.execute("SELECT id, section, line_start, line_end FROM chunks WHERE document_id = %s ORDER BY line_start", (doc_id,))
        chunks = cur.fetchall()
        cur.execute("SELECT id, title, updated_at FROM documents WHERE supersedes_id = %s", (doc_id,))
        succ = cur.fetchone()
        cur.execute("SELECT version_no, changed_at, change_summary, p.name AS changed_by FROM document_versions v LEFT JOIN people p ON p.id = v.changed_by WHERE document_id = %s ORDER BY version_no DESC", (doc_id,))
        versions = cur.fetchall()
        cur.execute("SELECT kind, note, created_at, p.name AS assignee FROM tasks t LEFT JOIN people p ON p.id = t.assignee_id WHERE document_id = %s AND NOT done ORDER BY created_at DESC", (doc_id,))
        open_tasks = cur.fetchall()
    d["country_name"] = COUNTRY_NAMES.get(d["country"]) if d["country"] else "Global"
    d["lines"] = d["body"].split("\n")
    d["chunks"] = chunks
    d["superseded_by"] = succ
    d["versions"] = versions
    d["open_tasks"] = open_tasks
    d["review_due"], d["review_period_days"] = freshness.review_due(d["doc_type"], d["updated_at"], d["validated_at"])
    return d


app.mount("/static", StaticFiles(directory=STATIC), name="static")
