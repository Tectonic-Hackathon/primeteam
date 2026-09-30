"""Step 2: split the question into sub-questions and generate rewrites per sub-question.

Each sub-question is later checked independently, which is what makes gap detection possible."""
import re
from ..taxonomy import REWRITES
from .context import detect_topics

_SPLIT = re.compile(r"\s*(?:,|;)?\s+and\s+(?=(?:which|what|how|who|where|when|is|are|does|do)\b)", re.I)


def plan(question: str, ctx: dict) -> list[dict]:
    parts = [p.strip(" ?") for p in _SPLIT.split(question) if p.strip(" ?")]
    if len(parts) == 1 and "?" in question.strip()[:-1]:
        parts = [p.strip() for p in question.split("?") if p.strip()]
    subs = []
    for i, p in enumerate(parts):
        topics = detect_topics(p) or ctx["topics"]
        rewrites = []
        for t in topics[:2]:
            rewrites.extend(REWRITES.get(t, []))
        # a rewrite that carries the resolved scope explicitly
        scope_words = " ".join(w for w in [ctx.get("country_name"), ctx.get("client")] if w)
        if scope_words:
            rewrites.append(f"{p} {scope_words}")
        subs.append({
            "id": f"Q{i + 1}",
            "text": p + "?",
            "topics": topics,
            "rewrites": rewrites[:4],
        })
    return subs
