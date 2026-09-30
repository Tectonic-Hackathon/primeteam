"""Keeping memory fresh: review periods per document type, staleness sweep, owner confirmation, orphan detection.

Freshness has three inputs: the last edit (updated_at), the owner's last confirmation (validated_at) and whether the source
still has the document (last_seen_at). Trust uses the most recent of edit/confirmation. The sweep turns overdue reviews into
tasks for owners; owners close them by editing (a sync picks it up) or by confirming the document is still valid."""
from datetime import date, timedelta
from .config import TODAY
from .taxonomy import HALF_LIFE_DAYS

# How long a document may go without an edit or an owner confirmation before we ask.
REVIEW_PERIOD_DAYS = {k: int(v * 1.2) for k, v in HALF_LIFE_DAYS.items()}


def effective_date(updated_at, validated_at):
    return max(d for d in (updated_at, validated_at) if d is not None)


def review_due(doc_type: str, updated_at, validated_at) -> tuple[bool, int]:
    today = date.fromisoformat(TODAY)
    period = REVIEW_PERIOD_DAYS.get(doc_type, 365)
    age = (today - effective_date(updated_at, validated_at)).days
    return age > period, period


def sweep(conn) -> dict:
    """Create confirm_valid tasks for overdue documents and reassign_owner tasks for documents whose owner left."""
    today = date.fromisoformat(TODAY)
    created = {"confirm_valid": 0, "reassign_owner": 0}
    with conn.cursor() as cur:
        cur.execute("""SELECT d.id, d.title, d.doc_type, d.updated_at, d.validated_at, d.owner_id, d.author_id, p.active AS owner_active
                       FROM documents d LEFT JOIN people p ON p.id = d.owner_id
                       WHERE d.status IN ('active', 'needs_update') AND d.doc_type NOT IN ('chat', 'email', 'ticket', 'meeting')""")
        for d in cur.fetchall():
            cur.execute("SELECT kind FROM tasks WHERE document_id = %s AND NOT done", (d["id"],))
            open_kinds = {r["kind"] for r in cur.fetchall()}
            if d["owner_id"] and d["owner_active"] is False and "reassign_owner" not in open_kinds:
                cur.execute("INSERT INTO tasks (kind, document_id, assignee_id, requested_by, note) VALUES ('reassign_owner', %s, NULL, 'freshness-sweep', %s)",
                            (d["id"], "Owner has left the company; document needs a new owner"))
                created["reassign_owner"] += 1
                continue
            due, period = review_due(d["doc_type"], d["updated_at"], d["validated_at"])
            if due and "confirm_valid" not in open_kinds and (d["owner_active"] or (d["owner_id"] is None and d["author_id"])):
                age = (today - effective_date(d["updated_at"], d["validated_at"])).days
                cur.execute("INSERT INTO tasks (kind, document_id, assignee_id, requested_by, note) VALUES ('confirm_valid', %s, %s, 'freshness-sweep', %s)",
                            (d["id"], d["owner_id"] or d["author_id"], f"Not edited or confirmed for {age} days (review period {period} days). Still valid?"))
                created["confirm_valid"] += 1
    return created


def overview(conn) -> dict:
    today = date.fromisoformat(TODAY)
    with conn.cursor() as cur:
        cur.execute("SELECT id, doc_type, updated_at, validated_at, status FROM documents WHERE status <> 'retracted'")
        docs = cur.fetchall()
        cur.execute("SELECT kind, count(*) AS n FROM tasks WHERE NOT done GROUP BY kind")
        tasks = {r["kind"]: r["n"] for r in cur.fetchall()}
        cur.execute("SELECT count(*) AS n FROM document_versions")
        versions = cur.fetchone()["n"]
        cur.execute("SELECT max(finished_at) AS t FROM sync_runs WHERE finished_at IS NOT NULL")
        last = cur.fetchone()["t"]
    overdue = sum(1 for d in docs if d["doc_type"] not in ("chat", "email", "ticket", "meeting") and review_due(d["doc_type"], d["updated_at"], d["validated_at"])[0])
    fresh = sum(1 for d in docs if (today - effective_date(d["updated_at"], d["validated_at"])).days <= 180)
    return {"documents": len(docs), "fresh_180d": fresh, "review_overdue": overdue, "open_tasks": tasks, "versions_recorded": versions,
            "last_sync": last.isoformat() + "Z" if last else None, "review_periods_days": REVIEW_PERIOD_DAYS}
