"""Step 4: deterministic trust signals per evidence chunk. Every number here is explainable in the UI."""
from datetime import date
from ..taxonomy import CHANNEL_WEIGHT, HALF_LIFE_DAYS, COUNTRY_NAMES
from ..config import TODAY


def _today() -> date:
    return date.fromisoformat(TODAY)


def score(chunk: dict, ctx: dict, people: dict, superseded_by: dict, reputation) -> dict:
    today = _today()
    validated = chunk.get("validated_at")
    eff = max(d for d in (chunk["updated_at"], validated) if d is not None)
    age = (today - eff).days
    hl = HALF_LIFE_DAYS.get(chunk["doc_type"], 365)
    freshness = 0.5 ** (age / hl)
    from ..freshness import review_due
    stale, period = review_due(chunk["doc_type"], chunk["updated_at"], validated)
    date_known = chunk.get("date_known", True)
    if not date_known:
        freshness, stale = 0.2, False

    owner = people.get(chunk["owner_id"]) if chunk["owner_id"] else None
    author = people.get(chunk["author_id"]) if chunk["author_id"] else None
    if owner and owner["active"]:
        owner_score, owner_note = 1.0, f"Owned by {owner['name']} ({owner['role']})"
    elif owner and not owner["active"]:
        owner_score, owner_note = 0.35, f"Owner {owner['name']} has left the company"
    elif author and author["active"]:
        owner_score, owner_note = 0.55, f"No formal owner, authored by {author['name']}"
    else:
        owner_score, owner_note = 0.15, "No owner or author on record"

    country = chunk["country"]
    if ctx.get("country") and country and country != ctx["country"]:
        scope, scope_note, in_scope = 0.0, f"Applies to {COUNTRY_NAMES.get(country, country)}, question is about {ctx['country_name']}", False
    elif country and ctx.get("country") == country:
        scope, scope_note, in_scope = 1.0, f"Applies to {COUNTRY_NAMES.get(country, country)}", True
    elif country is None:
        scope, scope_note, in_scope = 0.8, "Global document, not country specific", True
    else:
        scope, scope_note, in_scope = 0.7, f"Applies to {COUNTRY_NAMES.get(country, country)} (no country in question)", True
    if ctx.get("client") and chunk["client"] == ctx["client"]:
        scope = min(1.0, scope + 0.1)
        scope_note += f", specific to client {ctx['client']}"

    channel = CHANNEL_WEIGHT.get(chunk["doc_type"], 0.6)

    succ = superseded_by.get(chunk["document_id"])
    supersession = 0.15 if succ else 1.0

    rep_person = owner or author
    authority, authority_note = 0.3, "No author reputation available"
    if rep_person:
        r = reputation(rep_person["id"], chunk["doc_topics"] or [], chunk["country"])
        authority = min(1.0, 0.3 + r["normalized"] * 0.7)
        authority_note = f"{rep_person['name']} has {r['events']} recorded contributions on this topic"

    total = (0.30 * freshness + 0.20 * owner_score + 0.15 * authority + 0.15 * channel + 0.20 * supersession) * (1.0 if in_scope else 0.0)
    return {
        "total": round(total, 3),
        "in_scope": in_scope,
        "stale": stale,
        "unofficial": not owner and not author and not date_known,  # governance: no owner or date → never an official source
        "signals": {
            "freshness": {"value": round(freshness, 2), "note": "No date on record, so freshness cannot be assessed" if not date_known else (f"Owner confirmed still valid on {validated.isoformat()}" if validated and validated > chunk["updated_at"] else f"Updated {chunk['updated_at'].isoformat()}") + f" ({age} days ago); review period for a {chunk['doc_type']} is {period} days" + (", overdue" if stale else "")},
            "owner": {"value": round(owner_score, 2), "note": owner_note},
            "scope": {"value": round(scope, 2), "note": scope_note},
            "authority": {"value": round(authority, 2), "note": authority_note},
            "channel": {"value": round(channel, 2), "note": f"Source type: {chunk['doc_type']} via {chunk['source_system']}"},
            "supersession": {"value": round(supersession, 2), "note": f"Superseded by {succ['title']} ({succ['updated_at'].isoformat()})" if succ else "No newer version on record"},
        },
    }
