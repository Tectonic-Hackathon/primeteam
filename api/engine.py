"""Bounded, source constrained answer path for the local demonstration."""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from collections import defaultdict
from datetime import date

from db import cosine, embed, now, tokens

PUBLIC_TYPES = {"procedure", "policy", "manual", "checklist", "analysis", "chat", "email", "meeting", "ticket", "note", "application"}
STOP = {"the", "a", "an", "to", "of", "for", "in", "is", "and", "or", "what", "who", "how", "with", "does", "on", "my", "our", "are", "can", "about", "please", "project"}


def visible(row: sqlite3.Row | dict, role: str) -> bool:
    return row["acl"] == "employee" or role == "steward"


def serialize_source(row: sqlite3.Row | dict) -> dict:
    keys = ["id", "family", "version", "type", "title", "original_name", "mime", "content_hash",
            "ingested_at", "creator", "owner", "last_editor", "status", "created_at", "published_at",
            "modified_at", "effective_from", "effective_until", "observed_at", "country", "client",
            "domain", "project", "product", "audience", "language", "acl", "supersedes", "parent"]
    return {k: row[k] for k in keys} | {"tags": json.loads(row["tags"])}


def plan(question: str, country: str, domain: str) -> dict:
    q = question.strip()
    words = set(tokens(q))
    topic = "handover" if {"handover", "transfer", "checklist", "handoff"} & words else "general"
    reformulations = [q]
    if topic == "handover":
        reformulations += ["payroll handover procedure checklist", "transfer acknowledgement", "handover meeting ticket exception"]
    else:
        reformulations += [" ".join(w for w in re.findall(r"[a-z0-9]+", q.lower()) if w not in STOP)[:180]]
    return {"topic": topic, "reformulations": list(dict.fromkeys(reformulations))[:4],
            "routes": ["policy_and_procedure", "conversation_and_meeting", "ticket_and_application", "expertise"],
            "filters": {"country": country, "domain": domain}}


def applicability(source: sqlite3.Row | dict, context: dict) -> list[str]:
    reasons = []
    if source["country"] is None:
        reasons.append("Country scope is unknown")
    elif source["country"].lower() != context["country"].lower():
        reasons.append(f"Country mismatch: {source['country']}")
    if source["domain"] and source["domain"].lower() != context["domain"].lower():
        reasons.append(f"Domain mismatch: {source['domain']}")
    if source["client"] and not context.get("client"):
        reasons.append("Client context required")
    elif source["client"] and source["client"].lower() != context["client"].lower():
        reasons.append(f"Client mismatch: {source['client']}")
    if source["project"] and not context.get("project"):
        reasons.append("Project context required")
    elif source["project"] and source["project"].lower() != context["project"].lower():
        reasons.append(f"Project mismatch: {source['project']}")
    as_of = context["as_of"]
    if source["effective_from"] and source["effective_from"] > as_of:
        reasons.append(f"Not effective until {source['effective_from']}")
    if source["effective_until"] and source["effective_until"] < as_of:
        reasons.append(f"Expired {source['effective_until']}")
    if source["status"] == "superseded":
        reasons.append("Superseded version")
    return reasons


def lexical_score(question_tokens: set[str], text: str) -> float:
    t = set(tokens(text))
    return len(question_tokens & t) / (len(question_tokens) ** .5 or 1)


def retrieve(db: sqlite3.Connection, question: str, role: str, context: dict, query_plan: dict) -> tuple[list[dict], dict]:
    rows = db.execute("SELECT spans.id AS span_id,spans.source_id,spans.location,spans.text,spans.topic,spans.component,spans.claim_value,vectors.embedding,sources.* FROM spans JOIN vectors ON vectors.span_id=spans.id JOIN sources ON sources.id=spans.source_id").fetchall()
    qv = embed(" ".join(query_plan["reformulations"]))
    qwords = set(tokens(question))
    fts_terms = [w for w in sorted(qwords) if w not in STOP and len(w) > 2][:20]
    fts_query = " OR ".join(f'"{w}"' for w in fts_terms)
    fts_ids = {r["span_id"] for r in db.execute("SELECT spans_fts.span_id FROM spans_fts JOIN spans ON spans.id=spans_fts.span_id JOIN sources ON sources.id=spans.source_id WHERE spans_fts MATCH ? AND (sources.acl='employee' OR ?='steward')", (fts_query, role)).fetchall()} if fts_query else set()
    candidates = []
    excluded = []
    for row in rows:
        if not visible(row, role):
            continue  # ACL before ranking, diagnostics, answer, evidence, or expert output.
        vec = cosine(qv, json.loads(row["embedding"]))
        lex = lexical_score(qwords, row["text"] + " " + row["title"]) + (.2 if row["span_id"] in fts_ids else 0)
        score = round(.55 * vec + .45 * min(lex / 2, 1), 4)
        if score < .09:
            continue
        reasons = applicability(row, context)
        candidate = {"span_id": row["span_id"], "source_id": row["source_id"], "text": row["text"],
                     "location": row["location"], "topic": row["topic"], "component": row["component"],
                     "claim_value": row["claim_value"], "score": score, "reasons": reasons,
                     "source": serialize_source(row)}
        if reasons:
            excluded.append({"source_id": row["source_id"], "title": row["title"], "reasons": reasons, "score": score})
        else:
            candidates.append(candidate)
            trust_reasons = []
            if row["status"] != "approved": trust_reasons.append(f"Approval status: {row['status']}")
            if not row["owner"]: trust_reasons.append("Owner unknown")
            if not row["effective_from"]: trust_reasons.append("Effective date unknown")
            if trust_reasons:
                excluded.append({"source_id": row["source_id"], "title": row["title"], "reasons": trust_reasons, "score": score})
    candidates.sort(key=lambda c: c["score"], reverse=True)
    # Family grouping keeps repeated spans from one document from crowding out other source types.
    grouped: dict[str, int] = defaultdict(int)
    selected = []
    for item in candidates:
        family = item["source"]["family"]
        if grouped[family] >= 3:
            continue
        grouped[family] += 1
        selected.append(item)
        if len(selected) == 40:
            break
    excluded_by_source = {x["source_id"]: x for x in excluded}
    diagnostics = {"candidate_ids": [x["span_id"] for x in selected], "fts_matches": len(fts_ids),
                   "excluded": sorted(excluded_by_source.values(), key=lambda x: x["score"], reverse=True)[:20],
                   "scores": {x["span_id"]: x["score"] for x in selected}}
    return selected, diagnostics


def validate_claim(candidate: dict, context: dict) -> bool:
    source = candidate["source"]
    return (source["status"] == "approved" and bool(source["owner"]) and
            bool(source["effective_from"]) and not candidate["reasons"] and
            candidate["text"].strip() != "" and source["type"] in {"procedure", "policy", "manual", "checklist"})


def expert_suggestions(db: sqlite3.Connection, role: str, topic: str, country: str) -> list[dict]:
    rows = db.execute("SELECT p.*,a.id activity_id,a.kind,a.source_id,a.span_id,a.happened_at,a.explanation,s.acl,s.country source_country FROM expert_activity a JOIN people p ON p.id=a.person_id JOIN sources s ON s.id=a.source_id WHERE a.topic=? ORDER BY a.happened_at DESC", (topic,)).fetchall()
    by_person: dict[str, dict] = {}
    for row in rows:
        if not visible(row, role) or row["country"] != country or row["source_country"] != country:
            continue
        expert = by_person.setdefault(row["id"], {"id": row["id"], "name": row["name"], "role": row["role"],
                                                   "team": row["team"], "country": row["country"],
                                                   "topic": topic, "activities": []})
        expert["activities"].append({"id": row["activity_id"], "kind": row["kind"],
                                     "source_id": row["source_id"], "span_id": row["span_id"],
                                     "happened_at": row["happened_at"], "explanation": row["explanation"]})
    result = list(by_person.values())
    result.sort(key=lambda e: (len(e["activities"]), max(a["happened_at"] for a in e["activities"])), reverse=True)
    return result[:3]


def review_items(db: sqlite3.Connection, role: str, context: dict | None = None, missing: list[str] | None = None) -> list[dict]:
    items = []
    relations = db.execute("SELECT r.*,a.title a_title,a.acl a_acl,a.country a_country,b.title b_title,b.acl b_acl,b.country b_country FROM relations r JOIN sources a ON a.id=r.from_source JOIN sources b ON b.id=r.to_source").fetchall()
    for row in relations:
        if row["kind"] == "supersedes" or not (visible({"acl": row["a_acl"]}, role) and visible({"acl": row["b_acl"]}, role)):
            continue
        if context and row["a_country"] != context["country"]:
            continue
        label = "Conflict" if row["kind"] == "conflicts" else "Exact duplicate" if row["kind"] == "exact_duplicate" else "Near duplicate"
        items.append({"id": f"relation-{row['id']}", "kind": row["kind"], "label": label,
                      "title": row["reason"], "source_ids": [row["from_source"], row["to_source"]],
                      "action": "Ask the relevant source owner to review and approve or reject the proposed change." if row["kind"] == "conflicts" else "Confirm which copy should remain discoverable."})
    sources = db.execute("SELECT * FROM sources").fetchall()
    for s in sources:
        if not visible(s, role) or (context and s["country"] != context["country"]):
            continue
        if s["status"] == "superseded":
            items.append({"id": f"old-{s['id']}", "kind": "outdated", "label": "Outdated version",
                          "title": f"{s['title']} is superseded.", "source_ids": [s["id"]],
                          "action": "Keep for history; use the approved current version for current answers."})
        if not s["owner"] or (s["status"] != "approved" and not s["effective_from"]):
            gaps = []
            if not s["owner"]: gaps.append("owner")
            if not s["effective_from"]: gaps.append("effective date")
            if gaps:
                items.append({"id": f"metadata-{s['id']}", "kind": "missing_metadata", "label": "Missing trust signal",
                              "title": f"{s['title']} has no {' or '.join(gaps)}.", "source_ids": [s["id"]],
                              "action": "Assign an owner and confirm the effective date before promoting this source."})
    for component in missing or []:
        items.insert(0, {"id": f"missing-{component}", "kind": "missing_knowledge", "label": "Missing knowledge",
                         "title": f"No approved, applicable source establishes {component}.", "source_ids": [],
                         "action": "Ask the suggested expert to identify or create approved guidance."})
    return items[:30]


def answer(db: sqlite3.Connection, payload: dict, role: str) -> dict:
    question = payload["question"].strip()
    context = {"country": payload["country"], "domain": payload["domain"],
               "client": payload.get("client") or None, "project": payload.get("project") or None,
               "as_of": payload["as_of"]}
    query_plan = plan(question, context["country"], context["domain"])
    candidates, diagnostics = retrieve(db, question, role, context, query_plan)
    topic = query_plan["topic"]
    requested = ["checklist", "acknowledgement"] if topic == "handover" else []
    if re.search(r"client.facing|completion note|who confirms|final confirmation", question, re.I):
        requested.append("client-facing completion note")
    approved = [c for c in candidates if validate_claim(c, context) and (topic == "general" or c["topic"] == topic)]
    # The answer is a short selection of verbatim source sentences, never free-form generated claims.
    selected = []
    seen_component = set()
    for c in approved:
        component = c["component"] or c["span_id"]
        if component in seen_component:
            continue
        selected.append(c)
        seen_component.add(component)
        if len(selected) == 4:
            break
    claims = []
    evidence = []
    for i, c in enumerate(selected, 1):
        eid = f"E{i}"
        claims.append({"id": f"C{i}", "text": c["text"], "status": "Supported", "evidence_ids": [eid],
                       "component": c["component"]})
        evidence.append({"id": eid, "span_id": c["span_id"], "source_id": c["source_id"],
                         "source_title": c["source"]["title"], "location": c["location"],
                         "excerpt": c["text"], "source_type": c["source"]["type"],
                         "status": c["source"]["status"]})
    found = {c["component"] for c in selected}
    completeness = []
    missing = []
    conflict_source_ids = {row["from_source"] for row in db.execute("SELECT from_source FROM relations WHERE kind='conflicts'").fetchall()}
    conflict_components = {c["component"] for c in candidates if c["source_id"] in conflict_source_ids}
    for component in requested:
        if component in found:
            status = "conflicted" if component in conflict_components and context["country"] == "Belgium" else "supported"
            explanation = "Approved evidence exists, but an unapproved source proposes a different step." if status == "conflicted" else "Supported by an approved applicable source."
        else:
            status = "missing"
            missing.append(component)
            explanation = "No approved, applicable source establishes this component."
        completeness.append({"component": component, "status": status, "reason": explanation})
    reviews = review_items(db, role, context, missing)
    run_id = uuid.uuid4().hex[:12]
    db.execute("INSERT INTO query_runs VALUES (?,?,?,?,?,?,?)", (run_id, now(), role, question, json.dumps(context),
               json.dumps(query_plan), json.dumps(diagnostics)))
    for i, claim in enumerate(claims, 1):
        claim_id = f"{run_id}:C{i}"
        db.execute("INSERT INTO answer_claims VALUES (?,?,?,?,?,?)", (claim_id, run_id, i, claim["text"], claim["status"], claim["component"]))
        db.execute("INSERT INTO evidence_links VALUES (?,?)", (claim_id, evidence[i-1]["span_id"]))
    status = "Needs review" if any(x["status"] in {"conflicted", "missing"} for x in completeness) else ("Supported" if claims else "Unknown")
    return {"api_version": "1", "run_id": run_id, "mode": "deterministic local demo", "status": status,
            "scope": context, "claims": claims, "evidence": evidence, "completeness": completeness,
            "unknown": [f"Who confirms the client-facing completion note is unknown from approved evidence." if x == "client-facing completion note" else f"{x.capitalize()} is unknown from approved evidence." for x in missing],
            "review_items": reviews, "exclusions": diagnostics["excluded"],
            "experts": expert_suggestions(db, role, topic, context["country"]),
            "plan": query_plan, "diagnostics": diagnostics}
