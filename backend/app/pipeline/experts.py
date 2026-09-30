"""Step 7: reputation per person per topic per country, from the knowledge graph edges."""
from datetime import date
import math
from ..taxonomy import REL_WEIGHT, TOPIC_LABELS, CHANNEL_WEIGHT
from ..config import TODAY

_REL_VERB = {
    "owns": "owns", "authored": "authored", "edited": "edited", "answered": "answered a question in",
    "consulted": "was consulted on", "attended": "attended", "assigned": "is assigned", "reviewed": "reviewed",
}


class Reputation:
    def __init__(self, conn):
        self.today = date.fromisoformat(TODAY)
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM people")
            self.people = {p["id"]: p for p in cur.fetchall()}
            cur.execute("SELECT id, title, doc_type, topics, country, client, updated_at FROM documents")
            self.docs = {d["id"]: d for d in cur.fetchall()}
            cur.execute("SELECT * FROM edges WHERE src LIKE 'person:%'")
            self.edges = cur.fetchall()

    def _decay(self, at: date) -> float:
        return 0.5 ** ((self.today - at).days / 365)

    def _raw(self, pid: str, topics: list[str], country: str | None) -> dict:
        score, events, reasons = 0.0, 0, []
        for e in self.edges:
            if e["src"] != f"person:{pid}":
                continue
            kind, _, target = e["dst"].partition(":")
            if kind == "doc":
                d = self.docs.get(target)
                if not d:
                    continue
                if not (set(d["topics"] or []) & set(topics)):
                    continue
                scope = 1.0 if (country is None or d["country"] is None or d["country"] == country) else 0.3
                w = REL_WEIGHT.get(e["rel"], 0.5) * self._decay(e["at"]) * scope * CHANNEL_WEIGHT.get(d["doc_type"], 0.6)
                score += w
                events += 1
                reasons.append((w, f"{_REL_VERB.get(e['rel'], e['rel'])} \"{d['title']}\" on {e['at'].isoformat()}"))
            elif kind == "topic" and target in topics:
                w = REL_WEIGHT.get(e["rel"], 0.5) * self._decay(e["at"])
                score += w
                events += 1
                reasons.append((w, f"{_REL_VERB.get(e['rel'], e['rel'])} {TOPIC_LABELS.get(target, target)}" + (f": {e['note']}" if e["note"] else "")))
        p = self.people[pid]
        # seniority is a small tie-breaker only, capped
        score *= 1.0 + min(p["seniority_years"], 10) * 0.015
        reasons.sort(key=lambda r: -r[0])
        return {"score": score, "events": events, "reasons": [r for _, r in reasons[:8]]}

    def __call__(self, pid: str, topics: list[str], country: str | None) -> dict:
        r = self._raw(pid, topics, country)
        r["normalized"] = 1 - math.exp(-r["score"] / 2.5)  # saturating: 2.5 raw ≈ 63, 7.5 raw ≈ 95
        return r

    def find(self, topics: list[str], country: str | None, limit: int = 4) -> list[dict]:
        out = []
        for pid, p in self.people.items():
            if not p["active"]:
                continue
            r = self(pid, topics, country)
            if r["events"] == 0:
                continue
            out.append({
                "id": pid, "name": p["name"], "role": p["role"], "team": p["team"], "country": p["country"],
                "in_country": country is None or p["country"] is None or p["country"] == country,
                "seniority_years": p["seniority_years"], "email": p["email"],
                "score": round(r["normalized"] * 100), "reasons": r["reasons"], "events": r["events"],
                "topics": [TOPIC_LABELS.get(t, t) for t in topics],
                "initials": "".join(w[0] for w in p["name"].split()[:2]).upper(),
            })
        out.sort(key=lambda x: -x["score"])
        return out[:limit]
