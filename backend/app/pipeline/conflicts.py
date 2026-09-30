"""Step 5: make conflicting, duplicated, outdated and out-of-scope knowledge visible.

Clusters candidate chunks from *different* documents that talk about the same topic,
then compares the facts they state (first value per unit: days, weeks, %, €...)."""
import re
from ..embeddings import cosine

_FACT = re.compile(
    r"(€\s?\d+(?:[.,]\d+)?|£\s?\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s*(?:%|percent|calendar days|working days|days|weeks|months|years|hours|per week))",
    re.I,
)
_TOKEN = re.compile(r"[a-z0-9]+")
RELEVANT_FOR_REVIEW = 0.35


def facts(text: str) -> list[str]:
    out = []
    for m in _FACT.findall(text):
        f = re.sub(r"\s+", " ", m.strip().lower()).replace(",", ".")
        f = f.replace("calendar days", "days").replace("working days", "days").replace("percent", "%")
        out.append(f)
    seen, uniq = set(), []
    for f in out:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq


def _by_unit(fs: list[str]) -> dict[str, str]:
    """first value per unit, e.g. {'days': '30', 'weeks': '18', '€': '8'}"""
    units = {}
    for f in fs:
        m = re.match(r"([€£])\s?([\d.]+)", f)
        if m:
            units.setdefault(m.group(1), m.group(2))
            continue
        m = re.match(r"([\d.]+)\s*(.+)", f)
        if m:
            units.setdefault(m.group(2), m.group(1))
    return units


CONDITION_UNITS = {"years", "months of service", "years of service"}


def contradict(a: list[str], b: list[str]) -> list[tuple[str, str, str]]:
    """Values that differ for the same unit. If a *condition* differs too (e.g. 5 years vs 7 years of service),
    the two statements describe different cases and do not contradict each other."""
    ua, ub = _by_unit(a), _by_unit(b)
    if any(u in ua and u in ub and ua[u] != ub[u] for u in CONDITION_UNITS):
        return []
    return [(u, ua[u], ub[u]) for u in ua if u in ub and ua[u] != ub[u] and u not in CONDITION_UNITS]


def _tokens(s: str) -> set[str]:
    return set(_TOKEN.findall(s.lower()))


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / (len(ta | tb) or 1)


def _containment(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / (min(len(ta), len(tb)) or 1)


def _dedupe_by_doc(items: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for c in items:
        cur = best.get(c["document_id"])
        if cur is None or c["relevance"] > cur["relevance"]:
            best[c["document_id"]] = c
    return sorted(best.values(), key=lambda c: -c["relevance"])


def analyse(cands: list[dict], sub: dict, embeddings: dict) -> dict:
    """cands: retrieved chunks with 'trust' attached. Returns usable evidence + review buckets."""
    review = {"conflicts": [], "duplicates": [], "outdated": [], "out_of_scope": []}
    in_scope, oos, outdated = [], [], []
    for c in cands:
        topic_ok = bool(set(c["chunk_topics"] or []) & set(sub["topics"])) or not sub["topics"]
        if not c["trust"]["in_scope"]:
            if c["relevance"] >= RELEVANT_FOR_REVIEW and topic_ok:
                oos.append(c)
            continue
        if c["trust"]["signals"]["supersession"]["value"] < 1.0:
            if c["relevance"] >= RELEVANT_FOR_REVIEW and topic_ok:
                outdated.append(c)
            continue
        in_scope.append(c)
    review["out_of_scope"] = _dedupe_by_doc(oos)
    review["outdated"] = _dedupe_by_doc(outdated)

    # cluster relevant in-scope candidates across documents; same-document sections never cluster
    def on_topic(c):
        return not sub["topics"] or bool(set(c["chunk_topics"] or []) & set(sub["topics"]))
    clusterable = [c for c in in_scope if c["relevance"] >= RELEVANT_FOR_REVIEW and on_topic(c)]
    rest = [c for c in in_scope if c["relevance"] < RELEVANT_FOR_REVIEW or not on_topic(c)]
    clusters: list[list[dict]] = []
    for c in clusterable:
        placed = False
        for cl in clusters:
            if any(m["document_id"] == c["document_id"] for m in cl):
                continue
            head = cl[0]
            same_topic = bool(set(c["chunk_topics"] or []) & set(head["chunk_topics"] or []))
            if not same_topic:
                continue
            sim = cosine(embeddings[c["chunk_id"]], embeddings[head["chunk_id"]])
            if sim >= 0.80 or _jaccard(c["text"], head["text"]) >= 0.3 or _containment(c["text"], head["text"]) >= 0.8:
                cl.append(c)
                placed = True
                break
        if not placed:
            clusters.append([c])

    usable = []
    for cl in clusters:
        cl.sort(key=lambda c: -(c["relevance"] * 0.5 + c["trust"]["total"] * 0.5))
        winner = _pick_winner(cl)
        cl.remove(winner)
        cl.insert(0, winner)
        winner["contested"] = False
        usable.append(winner)
        wf = facts(winner["text"])
        for other in cl[1:]:
            if _containment(winner["text"], other["text"]) >= 0.8:
                review["duplicates"].append({"kept": winner, "duplicate": other})
                continue
            of = facts(other["text"])
            diffs = contradict(wf, of)
            if diffs:
                winner["contested"] = True
                review["conflicts"].append({
                    "winner": winner, "loser": other,
                    "winner_facts": wf, "loser_facts": of,
                    "diffs": [{"unit": u, "kept": a, "rejected": b} for u, a, b in diffs],
                    "reason": _why(winner, other),
                })
            else:
                other["contested"] = False
                other["supports"] = winner["chunk_id"]
                usable.append(other)  # complementary or confirming evidence
    for c in rest:
        c["contested"] = False
        usable.append(c)
    usable.sort(key=lambda c: -(c["relevance"] * 0.5 + c["trust"]["total"] * 0.5))
    return {"usable": usable, "review": review}


def _why(w: dict, l: dict) -> str:
    ws, ls = w["trust"]["signals"], l["trust"]["signals"]
    parts = []
    if ws["owner"]["value"] > ls["owner"]["value"]:
        parts.append("it has an accountable owner")
    if ws["channel"]["value"] > ls["channel"]["value"]:
        parts.append(f"a {w['doc_type']} outranks a {l['doc_type']}")
    if ws["authority"]["value"] > ls["authority"]["value"]:
        parts.append("its owner has more recorded expertise on this topic")
    if ws["freshness"]["value"] > ls["freshness"]["value"]:
        parts.append("it is more recent")
    lost = []
    if ls["freshness"]["value"] > ws["freshness"]["value"]:
        lost.append("the rejected source is newer")
    if not parts:
        parts.append("it scores higher overall")
    s = "Preferred because " + ", ".join(parts)
    if lost:
        s += ", even though " + " and ".join(lost)
    return s + "."


FORMAL_CHANNEL = 0.75   # policy, procedure, manual, checklist, wiki, analysis, meeting
ANSWERING = 0.5


def _pick_winner(cl: list[dict]) -> dict:
    """The brief's rule: when several sources answer the same question, take the latest one that has an owner,
    a date and the right scope. Tickets, chats and emails cannot win on recency alone."""
    top_rel = max(c["relevance"] for c in cl)
    qualified = [
        c for c in cl
        if c["relevance"] >= ANSWERING and c["relevance"] >= top_rel - 0.2
        and c["trust"]["signals"]["owner"]["value"] >= 1.0
        and c["trust"]["signals"]["channel"]["value"] >= FORMAL_CHANNEL
    ]
    if qualified:
        qualified.sort(key=lambda c: (c["updated_at"], c["trust"]["total"], c["relevance"]), reverse=True)
        return qualified[0]
    return cl[0]
