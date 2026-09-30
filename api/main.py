from __future__ import annotations

import html
import json
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field, field_validator

from db import connect, init_db, import_source, rebuild_index
from engine import answer, review_items, serialize_source, visible

MAX_UPLOAD = 2 * 1024 * 1024
ALLOWED_EXT = {".pdf", ".md", ".txt", ".json", ".eml"}
SOURCE_TYPES = {"policy", "manual", "procedure", "checklist", "analysis", "chat", "email", "meeting", "ticket", "note", "application"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Knowledge Trust local prototype", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Demo-Role"])


def role_from(value: str | None) -> str:
    if value not in {None, "employee", "steward"}:
        raise HTTPException(400, "Unknown demo role")
    return value or "employee"


def source_or_404(db: sqlite3.Connection, source_id: str, role: str):
    row = db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
    if not row or not visible(row, role):
        raise HTTPException(404, "Source not found")
    return row


class QueryIn(BaseModel):
    question: str = Field(min_length=5, max_length=600)
    country: str = Field(min_length=2, max_length=80)
    domain: str = Field(min_length=2, max_length=80)
    client: str | None = Field(default=None, max_length=80)
    project: str | None = Field(default=None, max_length=80)
    as_of: date

    @field_validator("question", "country", "domain")
    @classmethod
    def no_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Required field cannot be blank")
        return value.strip()


@app.get("/api/health")
def health():
    with connect() as db:
        count = db.execute("SELECT count(*) FROM sources").fetchone()[0]
        vectors = db.execute("SELECT count(*) FROM vectors").fetchone()[0]
        spans = db.execute("SELECT count(*) FROM spans").fetchone()[0]
        return {"status": "ready" if count and vectors == spans else "degraded", "database": "sqlite",
                "vector_index": "local concept-hash vectors", "lexical_index": "SQLite FTS5",
                "sources": count, "spans": spans, "vectors": vectors,
                "llm_provider": "unavailable; deterministic evidence mode active"}


@app.get("/api/sources")
def sources(x_demo_role: Annotated[str | None, Header()] = None):
    role = role_from(x_demo_role)
    with connect() as db:
        rows = db.execute("SELECT * FROM sources ORDER BY title,version DESC").fetchall()
        return {"sources": [serialize_source(row) for row in rows if visible(row, role)]}


@app.get("/api/sources/{source_id}")
def source_detail(source_id: str, x_demo_role: Annotated[str | None, Header()] = None):
    role = role_from(x_demo_role)
    with connect() as db:
        source = source_or_404(db, source_id, role)
        spans = db.execute("SELECT id,location,text,topic,component FROM spans WHERE source_id=? ORDER BY id", (source_id,)).fetchall()
        return {"source": serialize_source(source), "spans": [dict(s) for s in spans]}


@app.get("/api/sources/{source_id}/content")
def source_content(source_id: str, role: str | None = Query(None), x_demo_role: Annotated[str | None, Header()] = None):
    resolved_role = role_from(x_demo_role or role)
    with connect() as db:
        source = source_or_404(db, source_id, resolved_role)
        mime = source["mime"]
        return Response(content=source["original"], media_type=mime,
                        headers={"Content-Disposition": f"inline; filename=\"{re.sub(r'[^a-zA-Z0-9._-]', '_', source['original_name'])}\"",
                                 "X-Content-Type-Options": "nosniff"})


@app.get("/api/sources/{source_id}/original", response_class=HTMLResponse)
def original_view(source_id: str, span_id: str | None = None, role: str | None = Query(None), x_demo_role: Annotated[str | None, Header()] = None):
    resolved_role = role_from(x_demo_role or role)
    with connect() as db:
        source = source_or_404(db, source_id, resolved_role)
        if source["mime"] == "application/pdf":
            content_url = f"/api/sources/{source_id}/content?role={resolved_role}"
            return HTMLResponse(f'<title>{html.escape(source["title"])}</title><iframe title="Stored PDF" src="{content_url}#page=1" style="width:100%;height:98vh;border:0"></iframe>')
        text = source["original"].decode("utf-8", errors="replace")
        escaped = html.escape(text)
        if span_id:
            row = db.execute("SELECT text FROM spans WHERE id=? AND source_id=?", (span_id, source_id)).fetchone()
            if row:
                excerpt = html.escape(row["text"])
                escaped = escaped.replace(excerpt, f'<mark id="cited">{excerpt}</mark>', 1)
        title = html.escape(source["title"])
        return HTMLResponse(f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><style>body{{font:16px/1.7 system-ui;color:#152846;max-width:850px;margin:55px auto;padding:0 24px}}pre{{white-space:pre-wrap;word-break:break-word;background:#f4f7fb;padding:28px;border-radius:14px}}mark{{background:#ffe49a}}small{{color:#61718a}}</style></head><body><small>SYNTHETIC DEMO SOURCE · stored original</small><h1>{title}</h1><pre>{escaped}</pre><script>document.getElementById("cited")?.scrollIntoView()</script></body></html>')


@app.get("/api/evidence/{span_id:path}")
def evidence(span_id: str, x_demo_role: Annotated[str | None, Header()] = None):
    role = role_from(x_demo_role)
    with connect() as db:
        row = db.execute("SELECT spans.id AS span_id,spans.location,spans.text,sources.* FROM spans JOIN sources ON sources.id=spans.source_id WHERE spans.id=?", (span_id,)).fetchone()
        if not row or not visible(row, role):
            raise HTTPException(404, "Evidence not found")
        return {"id": row["span_id"], "excerpt": row["text"], "location": row["location"],
                "source": serialize_source(row)}


@app.post("/api/query")
def query(payload: QueryIn, x_demo_role: Annotated[str | None, Header()] = None):
    role = role_from(x_demo_role)
    with connect() as db:
        return answer(db, payload.model_dump(mode="json"), role)


@app.get("/api/review-items")
def reviews(country: str | None = None, x_demo_role: Annotated[str | None, Header()] = None):
    role = role_from(x_demo_role)
    with connect() as db:
        return {"items": review_items(db, role, {"country": country} if country else None)}


@app.post("/api/sources/import")
async def upload_source(metadata: Annotated[str, Form()], file: Annotated[UploadFile, File()],
                        x_demo_role: Annotated[str | None, Header()] = None):
    role = role_from(x_demo_role)
    if role != "steward":
        raise HTTPException(403, "Only the demo steward may import sources")
    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(422, "Metadata must be valid JSON")
    if not isinstance(meta, dict) or not all(meta.get(k) for k in ("id", "type", "title", "country", "domain")):
        raise HTTPException(422, "Metadata requires id, type, title, country, and domain")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", str(meta["id"])):
        raise HTTPException(422, "Source ID must use 1–80 letters, numbers, hyphens, or underscores")
    if any(len(str(meta[k])) > 200 for k in ("title", "country", "domain")):
        raise HTTPException(422, "Metadata value is too long")
    if meta["type"] not in SOURCE_TYPES:
        raise HTTPException(422, "Unsupported source type")
    filename = file.filename or ""
    if not any(filename.lower().endswith(ext) for ext in ALLOWED_EXT):
        raise HTTPException(422, "Unsupported file extension")
    raw = await file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "File exceeds 2 MB local demo limit")
    if not raw:
        raise HTTPException(422, "File is empty")
    mime = "application/pdf" if filename.lower().endswith(".pdf") else "application/json" if filename.lower().endswith(".json") else "text/plain"
    meta["mime"] = mime
    meta["original_name"] = filename
    meta["status"] = "draft"  # uploads never silently become approved policy
    meta["acl"] = "employee" if meta.get("acl") != "steward" else "steward"
    try:
        with connect() as db:
            return import_source(db, meta, raw)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(422, str(exc))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Source ID already exists")


@app.post("/api/index/rebuild")
def rebuild(x_demo_role: Annotated[str | None, Header()] = None):
    if role_from(x_demo_role) != "steward":
        raise HTTPException(403, "Only the demo steward may rebuild the index")
    with connect() as db:
        return {"indexed_spans": rebuild_index(db)}
