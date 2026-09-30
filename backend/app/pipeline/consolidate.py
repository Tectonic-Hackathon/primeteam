"""Step 8: consolidate per-sub-question evidence into one grounded answer with E1..En citations.

Deterministic by design for the first iteration: every sentence in the answer is a verbatim
evidence passage, so grounding is guaranteed. An LLM writer can be swapped in behind the same interface."""
import re
from ..taxonomy import COUNTRY_NAMES, STOPWORDS

_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_TOK = re.compile(r"[a-z0-9€£%]+")


def split_lead(question: str, text: str) -> tuple[str, str]:
    """Return (lead sentence, remaining text). The lead is the sentence sharing most content words with the question."""
    sents = [x.strip() for x in _SENT.split(text) if x.strip()]
    if len(sents) <= 1:
        return text, ""
    qt = {t for t in _TOK.findall(question.lower()) if t not in STOPWORDS and len(t) > 2}
    def overlap(sent):
        st = {t for t in _TOK.findall(sent.lower()) if t not in STOPWORDS}
        return len(qt & st) + (0.5 if re.search(r"\d", sent) else 0)
    best = max(range(len(sents)), key=lambda i: (overlap(sents[i]), -i))
    rest = " ".join(x for i, x in enumerate(sents) if i != best)
    return sents[best], rest

RELEVANCE_MIN = 0.5
RELATED_MIN = 0.35
TRUST_MIN = 0.35
INFORMAL = {"chat", "email", "ticket"}


FORMAL_CHANNEL = 0.75


def pick_primary(strong: list[dict]) -> dict:
    """Among passages that all answer the question, prefer the latest one with an accountable owner and a formal
    channel (policy, procedure, manual, meeting decision...). Informal sources only win when nothing formal exists."""
    top_rel = strong[0]["relevance"]
    qualified = [c for c in strong
                 if c["relevance"] >= top_rel - 0.2
                 and c["trust"]["signals"]["owner"]["value"] >= 1.0
                 and c["trust"]["signals"]["channel"]["value"] >= FORMAL_CHANNEL]
    if qualified:
        qualified.sort(key=lambda c: (c["updated_at"], c["trust"]["total"], c["relevance"]), reverse=True)
        return qualified[0]
    return strong[0]


def _evidence_card(c: dict, eid: str, people: dict) -> dict:
    owner = people.get(c["owner_id"]) if c["owner_id"] else None
    author = people.get(c["author_id"]) if c["author_id"] else None
    return {
        "id": eid,
        "chunk_id": c["chunk_id"],
        "document_id": c["document_id"],
        "title": c["title"],
        "doc_type": c["doc_type"],
        "source_system": c["source_system"],
        "section": c["section"],
        "line_start": c["line_start"],
        "line_end": c["line_end"],
        "text": c["text"],
        "country": c["country"],
        "country_name": COUNTRY_NAMES.get(c["country"]) if c["country"] else "Global",
        "client": c["client"],
        "owner": owner["name"] if owner else None,
        "owner_role": owner["role"] if owner else None,
        "owner_active": owner["active"] if owner else None,
        "author": author["name"] if author else None,
        "updated_at": c["updated_at"].isoformat(),
        "version": c["version"],
        "location": c["location"],
        "url": c["url"],
        "relevance": c["relevance"],
        "trust": c["trust"],
        "status": c.get("status", "active"),
        "validated_at": c["validated_at"].isoformat() if c.get("validated_at") else None,
        "stale": c["trust"].get("stale", False),
        "owner_id": c["owner_id"],
        "author_id": c["author_id"],
        "confidence": round(0.5 * min(1.0, c["relevance"] / 0.8) + 0.5 * c["trust"]["total"], 2),
        "contested": c.get("contested", False),
    }


def consolidate(question: str, ctx: dict, subs: list[dict], per_sub: list[dict], experts_for_gaps, people: dict) -> dict:
    evidence: list[dict] = []
    ev_index: dict[int, str] = {}
    review = {"conflicts": [], "duplicates": [], "outdated": [], "out_of_scope": [], "stale": []}

    def cite(c: dict) -> str:
        if c["chunk_id"] in ev_index:
            return ev_index[c["chunk_id"]]
        eid = f"E{len(evidence) + 1}"
        ev_index[c["chunk_id"]] = eid
        evidence.append(_evidence_card(c, eid, people))
        return eid

    sections = []
    confidences = []
    for sub, res in zip(subs, per_sub):
        usable = res["usable"]
        on_topic = [c for c in usable if not sub["topics"] or set(sub["topics"]) & set(c["chunk_topics"] or [])]
        strong = [c for c in on_topic if c["relevance"] >= RELEVANCE_MIN and c["trust"]["total"] >= TRUST_MIN]
        related = [c for c in on_topic if RELATED_MIN <= c["relevance"] < RELEVANCE_MIN or (c["relevance"] >= RELEVANCE_MIN and c["trust"]["total"] < TRUST_MIN)]
        segments = []
        note = None
        if strong:
            primary = pick_primary(strong)
            lead, rest = split_lead(sub["text"], primary["text"])
            segments.append({"text": primary["text"], "lead": lead, "rest": rest, "evidence": [cite(primary)], "kind": "primary"})
            seen_docs = {primary["document_id"]}
            for extra in [c for c in strong if c is not primary][:3]:
                if extra["document_id"] in seen_docs:
                    continue
                seen_docs.add(extra["document_id"])
                if extra.get("supports") == primary["chunk_id"]:
                    kind = "earlier" if extra["updated_at"] < primary["updated_at"] and extra["doc_type"] in INFORMAL else "confirms"
                else:
                    kind = "supporting"
                segments.append({"text": extra["text"], "evidence": [cite(extra)], "kind": kind})
            conf = 0.5 * min(1.0, primary["relevance"] / 0.8) + 0.5 * primary["trust"]["total"]
            status = "answered"
            experts = []
            if primary.get("contested"):
                conf -= 0.15
                status = "contested"
                note = "Another source states a different value. The preferred source is shown; see the review tab."
                experts = experts_for_gaps(sub["topics"], ctx.get("country"))
            elif primary["doc_type"] in INFORMAL:
                status = "informal"
                conf -= 0.1
                note = f"The best evidence is a {primary['doc_type']}, not an owned document. Confirm with the people below."
                experts = experts_for_gaps(sub["topics"], ctx.get("country"))
            confidences.append(max(0.0, conf))
        elif related:
            primary = related[0]
            segments.append({"text": primary["text"], "evidence": [cite(primary)], "kind": "weak"})
            confidences.append(0.3 * primary["trust"]["total"])
            status = "partial"
            note = "Related material was found but nothing that answers this directly."
            experts = experts_for_gaps(sub["topics"], ctx.get("country"))
        else:
            status = "missing"
            note = "No grounded evidence in the knowledge base. The people below are the most likely to know."
            confidences.append(0.0)
            experts = experts_for_gaps(sub["topics"], ctx.get("country"))

        for item in res["review"]["conflicts"]:
            review["conflicts"].append({
                "question": sub["text"],
                "kept": _evidence_card(item["winner"], cite(item["winner"]), people),
                "rejected": _evidence_card(item["loser"], f"R{len(review['conflicts']) + 1}", people),
                "kept_facts": item["winner_facts"], "rejected_facts": item["loser_facts"],
                "diffs": item["diffs"], "reason": item["reason"],
            })
        for item in res["review"]["duplicates"]:
            review["duplicates"].append({
                "question": sub["text"],
                "kept": _evidence_card(item["kept"], cite(item["kept"]), people),
                "duplicate": _evidence_card(item["duplicate"], f"D{len(review['duplicates']) + 1}", people),
            })
        for c in res["review"]["outdated"]:
            review["outdated"].append({"question": sub["text"], "item": _evidence_card(c, f"O{len(review['outdated']) + 1}", people)})
        for c in res["review"]["out_of_scope"]:
            review["out_of_scope"].append({"question": sub["text"], "item": _evidence_card(c, f"S{len(review['out_of_scope']) + 1}", people)})
        for c in strong[:3] if strong else []:
            if c["trust"].get("stale") and c["document_id"] not in {x["item"]["document_id"] for x in review["stale"]}:
                review["stale"].append({"question": sub["text"], "item": _evidence_card(c, cite(c), people)})

        sections.append({
            "id": sub["id"], "question": sub["text"], "status": status,
            "topics": sub["topics"], "rewrites": sub["rewrites"],
            "segments": segments, "experts": experts, "note": note,
            "candidates_considered": len(usable) + sum(len(v) for v in res["review"].values()),
        })

    overall = sum(confidences) / len(confidences) if confidences else 0.0
    statuses = [s["status"] for s in sections]
    if all(s == "answered" for s in statuses):
        verdict = "Grounded answer"
    elif any(s in ("answered", "contested", "informal") for s in statuses) and any(s in ("missing", "partial") for s in statuses):
        verdict = "Partial answer, gap highlighted"
    elif any(s == "contested" for s in statuses):
        verdict = "Grounded answer, conflict flagged"
    elif any(s == "informal" for s in statuses):
        verdict = "Answer from informal sources"
    elif all(s == "missing" for s in statuses):
        verdict = "No grounded answer found"
    else:
        verdict = "Low confidence answer"

    review_count = sum(len(v) for v in review.values())
    return {
        "question": question,
        "context": ctx,
        "verdict": verdict,
        "status": c.get("status", "active"),
        "validated_at": c["validated_at"].isoformat() if c.get("validated_at") else None,
        "stale": c["trust"].get("stale", False),
        "owner_id": c["owner_id"],
        "author_id": c["author_id"],
        "confidence": round(overall, 2),
        "sections": sections,
        "evidence": evidence,
        "review": review,
        "review_count": review_count,
    }
