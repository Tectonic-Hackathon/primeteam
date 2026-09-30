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


# Non-numeric facts that still contradict: key → [(value, pattern)]
KEYFACTS = {
    "correction run cost": [("free", r"\bfor free\b|\bfree of charge\b|\bis free\b|\balways .{0,30}free\b"), ("charged", r"\bcharged\b|\bcosts? extra\b|\bnot free\b|\bpaid\b|\binvoiced\b")],
    "correction run availability": [("not available", r"correction runs? (?:are|is) not available"), ("available", r"correction run (?:can be requested|is possible|is available)")],
    "exceptions after cutoff": [("none", r"\bno exceptions\b"), ("some", r"\bonly [^.]{0,80} can be (?:processed|handled) after\b|\bexceptions? (?:are|is) (?:allowed|possible)\b|\bcan be handled after the cutoff\b")],
}


def keyfacts(text: str) -> list[str]:
    t = text.lower()
    out = []
    for key, options in KEYFACTS.items():
        for value, pat in options:
            if re.search(pat, t):
                out.append(f"{key}={value}")
                break
    return out


_REPORTED = re.compile(r"\b(?:say|says|said|claims?|told me|according to)\b[^.]{0,60}\d", re.I)
_NON_ANSWER = re.compile(r"does not determine|do not determine|is not determined|not covered by|out of scope|does not cover|must not be used|cannot be used to|is not part of", re.I)
_SELF_STALE = re.compile(r"old (?:onboarding )?(?:note|file|document|material|version)|have not checked|previous process|not (?:yet )?verified|i believe", re.I)


def asserts(text: str) -> bool:
    """A question or reported speech ("the old file says 100%") does not assert anything and cannot contradict."""
    if not text.strip():
        return False
    last = re.split(r"(?<=[.!?])\s+", text.strip())[-1]
    if last.endswith("?") or "?" in text[:120].split(".")[0]:
        return False
    return not _REPORTED.search(text)


def non_answer(text: str) -> bool:
    """A passage that explicitly says the topic is not determined here. It must not be presented as the answer."""
    return bool(_NON_ANSWER.search(text))


def facts(text: str) -> list[str]:
    out = keyfacts(text)
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
        if "=" in f and not f[0].isdigit():
            k, v = f.split("=", 1)
            units.setdefault(k, v)
            continue
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


def _is_duplicate(a: str, b: str) -> bool:
    """A copy, not merely a short passage that happens to be contained in a longer one."""
    ta, tb = _tokens(a), _tokens(b)
    if min(len(ta), len(tb)) < 20:
        return _jaccard(a, b) >= 0.75
    return _jaccard(a, b) >= 0.5 or _containment(a, b) >= 0.85


def _dedupe_by_doc(items: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for c in items:
        cur = best.get(c["document_id"])
        if cur is None or c["relevance"] > cur["relevance"]:
            best[c["document_id"]] = c
    return sorted(best.values(), key=lambda c: -c["relevance"])


def analyse(cands: list[dict], sub: dict, embeddings: dict) -> dict:
    """cands: retrieved chunks with 'trust' attached. Returns usable evidence + review buckets."""
    review = {"conflicts": [], "duplicates": [], "outdated": [], "out_of_scope": [], "unofficial": []}
    in_scope, oos, outdated, unofficial = [], [], [], []
    disclaimers = []
    for c in cands:
        topic_ok = bool(set(c["chunk_topics"] or []) & set(sub["topics"])) or not sub["topics"]
        if non_answer(c["text"]) and c["relevance"] >= RELEVANT_FOR_REVIEW and c["trust"]["in_scope"]:
            c["disclaimer"] = True
            disclaimers.append(c)
            continue
        if c["trust"].get("unofficial"):
            if c["relevance"] >= RELEVANT_FOR_REVIEW and topic_ok:
                unofficial.append(c)
            continue
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
    unofficial = _dedupe_by_doc(unofficial)

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
            if not same_topic or (c["country"] or head["country"]) and c["country"] != head["country"]:
                continue
            sim = cosine(embeddings[c["chunk_id"]], embeddings[head["chunk_id"]])
            shared_key = bool({f.split("=")[0] for f in keyfacts(c["text"])} & {f.split("=")[0] for f in keyfacts(head["text"])})
            if sim >= 0.80 or _jaccard(c["text"], head["text"]) >= 0.3 or _containment(c["text"], head["text"]) >= 0.8 or shared_key:
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
            if _is_duplicate(winner["text"], other["text"]):
                review["duplicates"].append({"kept": winner, "duplicate": other})
                continue
            of = facts(other["text"])
            diffs = contradict(wf, of) if asserts(other["text"]) else []
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
    # unofficial documents: never evidence, but say what they resemble and where they differ
    for c in unofficial:
        best, best_j = None, 0.0
        for u in usable:
            j = _jaccard(c["text"], u["text"])
            if j > best_j and set(c["chunk_topics"] or []) & set(u["chunk_topics"] or []):
                best, best_j = u, j
        entry = {"item": c}
        if best and best_j >= 0.2:
            entry["resembles"] = best
            entry["diffs"] = [{"unit": u, "kept": a, "rejected": b} for u, a, b in contradict(facts(best["text"]), facts(c["text"]))]
        review["unofficial"].append(entry)
    # contradictions inside one document: a retained old paragraph against the section that answers
    seen_pairs = set()
    for w in [u for u in usable if u["relevance"] >= ANSWERING]:
        wf = facts(w["text"])
        if not wf:
            continue
        for o in cands:
            if o["document_id"] != w["document_id"] or o["chunk_id"] == w["chunk_id"] or o.get("disclaimer"):
                continue
            pair = frozenset((w["chunk_id"], o["chunk_id"]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            diffs = contradict(wf, facts(o["text"])) if asserts(o["text"]) else []
            if diffs:
                w["contested"] = True
                review["conflicts"].append({
                    "winner": w, "loser": o, "winner_facts": wf, "loser_facts": facts(o["text"]),
                    "diffs": [{"unit": u, "kept": a, "rejected": b} for u, a, b in diffs],
                    "same_document": True,
                    "reason": f"Both passages are in the same document. The section \"{w['section']}\" states the current rule; the section \"{o['section']}\" "
                              + ("says itself that it belongs to the previous process." if _SELF_STALE.search(o["text"]) else "contradicts it and needs review by the owner."),
                })
    usable.sort(key=lambda c: -(c["relevance"] * 0.5 + c["trust"]["total"] * 0.5))
    return {"usable": usable, "review": review, "disclaimers": sorted(disclaimers, key=lambda c: -c["relevance"])}


OFFICIAL = {"policy", "procedure", "manual"}


def _why(w: dict, l: dict) -> str:
    ws, ls = w["trust"]["signals"], l["trust"]["signals"]
    parts = []
    if ws["owner"]["value"] > ls["owner"]["value"]:
        parts.append("it has an accountable owner")
    if w["doc_type"] in OFFICIAL and l["doc_type"] not in OFFICIAL:
        parts.append(f"an official {w['doc_type']} leads over a {l['doc_type']} (knowledge governance policy)")
    elif ws["channel"]["value"] > ls["channel"]["value"]:
        parts.append(f"a {w['doc_type']} outranks a {l['doc_type']}")
    if ws["authority"]["value"] > ls["authority"]["value"]:
        parts.append("its owner has more recorded expertise on this topic")
    if ws["freshness"]["value"] > ls["freshness"]["value"]:
        parts.append("it is more recent")
    if _SELF_STALE.search(l["text"]):
        parts.append("the rejected source says itself that it relies on old material")
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
        # official procedures/policies/manuals lead over notes, checklists and meeting notes; within a tier the latest wins
        qualified.sort(key=lambda c: (c["doc_type"] in OFFICIAL, c["updated_at"], c["trust"]["total"], c["relevance"]), reverse=True)
        return qualified[0]
    return cl[0]
