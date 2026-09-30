from .sharepoint import SharePointConnector
from .confluence import ConfluenceConnector
from .jira import JiraConnector
from .teams import TeamsConnector
from .outlook import OutlookConnector
from .meetings import MeetingsConnector, unit_from_transcript
from .ingest import upsert
from .base import KnowledgeUnit

REGISTRY = {c.name: c for c in [SharePointConnector(), ConfluenceConnector(), TeamsConnector(), OutlookConnector(), JiraConnector(), MeetingsConnector()]}


def statuses(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT ON (connector) connector, mode, fetched, inserted, updated, unchanged, archived, trigger, finished_at
                       FROM sync_runs WHERE finished_at IS NOT NULL ORDER BY connector, finished_at DESC""")
        last = {r["connector"]: r for r in cur.fetchall()}
        cur.execute("SELECT source_system, count(*) AS n FROM documents WHERE status <> 'retracted' GROUP BY source_system")
        counts = {r["source_system"]: r["n"] for r in cur.fetchall()}
    out = []
    for c in REGISTRY.values():
        s = c.status()
        lr = last.get(c.name)
        s["last_sync"] = {**{k: lr[k] for k in ("mode", "fetched", "inserted", "updated", "unchanged", "archived", "trigger")}, "finished_at": lr["finished_at"].isoformat() + "Z"} if lr else None
        s["documents"] = counts.get(c.source_system, 0)
        out.append(s)
    return out


def last_success(conn, name: str):
    with conn.cursor() as cur:
        cur.execute("SELECT finished_at FROM sync_runs WHERE connector = %s AND finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 1", (name,))
        r = cur.fetchone()
    return r["finished_at"].date().isoformat() if r else None


def sync(conn, name: str, since: str | None = None, trigger: str = "manual", full: bool = False) -> dict:
    """Delta sync by default: fetch what changed since the last successful run. `full` also archives documents
    that disappeared from the source."""
    c = REGISTRY[name]
    if since is None and not full:
        since = last_success(conn, name)
    units = c.fetch(None if full else since)
    return upsert(conn, c, units, since=since, trigger=trigger, full=full)
