"""Connector contract. Every source (SharePoint, Teams, Outlook, Jira, Confluence, meetings) yields KnowledgeUnits.

A connector is *live* when its credentials are present in the environment, otherwise it runs in *demo* mode and reads
fixtures/<name>.json so the whole flow works offline. The request shapes in each live implementation are the real ones."""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class KnowledgeUnit:
    external_id: str                 # stable id in the source system
    title: str
    doc_type: str                    # policy, procedure, manual, checklist, wiki, meeting, ticket, chat, email, analysis
    sections: list[tuple[str, list[str]]]   # (heading, sentences)
    updated_at: str                  # ISO date
    created_at: str | None = None
    owner_email: str | None = None
    author_email: str | None = None
    attendee_emails: list[str] = field(default_factory=list)
    country: str | None = None
    client: str | None = None
    team: str | None = None
    product: str | None = None
    topics: list[str] = field(default_factory=list)
    version: str | None = None
    location: str = ""
    url: str = ""

    def to_dict(self):
        return asdict(self)


class Connector:
    name: str = ""                   # registry key, e.g. "sharepoint"
    label: str = ""                  # UI label
    source_system: str = ""          # value stored on documents
    description: str = ""
    id_prefix: str = ""              # document id prefix, e.g. "SP"
    required_env: tuple[str, ...] = ()
    docs_url: str = ""

    @property
    def configured(self) -> bool:
        return all(os.getenv(k) for k in self.required_env)

    @property
    def mode(self) -> str:
        return "live" if self.configured else "demo"

    def fetch(self, since: str | None = None) -> list[KnowledgeUnit]:
        if self.configured:
            return self.fetch_live(since)
        return self.fetch_demo()

    def fetch_live(self, since: str | None) -> list[KnowledgeUnit]:  # pragma: no cover - needs credentials
        raise NotImplementedError

    def fetch_demo(self) -> list[KnowledgeUnit]:
        path = FIXTURES / f"{self.name}.json"
        if not path.exists():
            return []
        raw = json.loads(path.read_text())
        return [self.parse_fixture(item) for item in raw]

    def parse_fixture(self, item: dict) -> KnowledgeUnit:
        """Fixtures mimic the *raw* API payload of the source so the same parser is exercised in demo mode."""
        raise NotImplementedError

    def status(self) -> dict:
        return {
            "name": self.name, "label": self.label, "source_system": self.source_system, "description": self.description,
            "mode": self.mode, "required_env": list(self.required_env), "docs_url": self.docs_url,
        }


def sentences(text: str) -> list[str]:
    import re
    text = re.sub(r"\s+", " ", text or "").strip()
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9€£\"'(])", text) if s.strip()]
