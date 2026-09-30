"""Step 1: resolve the context a question is asked in (country, client, team, intent, topics)."""
import re
from ..taxonomy import COUNTRIES, COUNTRY_NAMES, CLIENTS, CLIENT_EMPLOYEES, TEAMS, TOPICS, INTENTS


def _contains(text: str, phrase: str) -> bool:
    return re.search(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", text) is not None


def detect_topics(text: str) -> list[str]:
    t = text.lower()
    scored = []
    for topic, kws in TOPICS.items():
        hits = [k for k in kws if _contains(t, k)]
        if hits:
            # longer keyword matches are stronger signals
            scored.append((max(len(k) for k in hits), topic))
    scored.sort(reverse=True)
    return [t for _, t in scored]


def resolve(question: str, user: dict | None = None) -> dict:
    q = question.lower()
    country, country_source = None, None
    client = None
    for name, c in CLIENTS.items():
        if _contains(q, name.lower()):
            client, country, country_source = name, c, f"client {name} is a {COUNTRY_NAMES[c]} account"
            break
    if not client:
        for emp, cl in CLIENT_EMPLOYEES.items():
            if _contains(q, emp):
                client, country = cl, CLIENTS[cl]
                country_source = f"{emp.title()} is an employee of client {cl} ({COUNTRY_NAMES[country]}), per the HR system"
                break
    if not country:
        for code, kws in COUNTRIES.items():
            if any(_contains(q, k) for k in kws):
                country, country_source = code, "mentioned in the question"
                break
    if not country and user and user.get("country"):
        country, country_source = user["country"], f"inferred from your profile ({user.get('name')})"

    team, team_hits = None, 0
    for name, kws in TEAMS.items():
        hits = sum(1 for k in kws if _contains(q, k))
        if hits > team_hits:
            team, team_hits = name, hits

    intent = "rule"
    for name, kws in INTENTS.items():
        if any(_contains(q, k) for k in kws):
            intent = name
            break

    return {
        "country": country,
        "country_name": COUNTRY_NAMES.get(country) if country else None,
        "country_source": country_source,
        "client": client,
        "team": team,
        "intent": intent,
        "topics": detect_topics(question),
    }
