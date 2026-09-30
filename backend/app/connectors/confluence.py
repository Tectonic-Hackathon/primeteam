"""Confluence Cloud pages via REST API v1 (content endpoint with body.storage)."""
import os
import re
import httpx
from .base import Connector, KnowledgeUnit, sentences


class ConfluenceConnector(Connector):
    name = "confluence"
    label = "Confluence"
    source_system = "Confluence"
    description = "Manuals and procedures from Confluence spaces (REST API, body.storage)."
    id_prefix = "CF"
    required_env = ("ATLASSIAN_URL", "ATLASSIAN_EMAIL", "ATLASSIAN_TOKEN", "CONFLUENCE_SPACES")
    docs_url = "https://developer.atlassian.com/cloud/confluence/rest/v1/api-group-content/"

    def fetch_live(self, since):
        base = os.environ["ATLASSIAN_URL"].rstrip("/")
        auth = (os.environ["ATLASSIAN_EMAIL"], os.environ["ATLASSIAN_TOKEN"])
        units = []
        for space in os.environ["CONFLUENCE_SPACES"].split(","):
            start = 0
            while True:
                r = httpx.get(f"{base}/wiki/rest/api/content", auth=auth, timeout=60,
                              params={"spaceKey": space.strip(), "type": "page", "expand": "body.storage,version,history,metadata.labels,ancestors", "limit": 50, "start": start})
                r.raise_for_status()
                data = r.json()
                units += [self.parse_fixture(p) for p in data.get("results", [])]
                if data.get("size", 0) < 50:
                    break
                start += 50
        return units

    def parse_fixture(self, page):
        html = page["body"]["storage"]["value"]
        labels = [l["name"] for l in page.get("metadata", {}).get("labels", {}).get("results", [])]
        doc_type = next((l for l in labels if l in ("manual", "procedure", "policy", "checklist", "analysis")), "wiki")
        country = next((l.upper() for l in labels if l.upper() in ("BE", "NL", "DE", "FR", "UK")), None)
        secs = []
        for m in re.finditer(r"<h2>(.*?)</h2>(.*?)(?=<h2>|$)", html, re.S):
            text = re.sub(r"<[^>]+>", " ", m.group(2))
            secs.append((re.sub(r"<[^>]+>", "", m.group(1)).strip(), sentences(text)))
        if not secs:
            secs.append(("Content", sentences(re.sub(r"<[^>]+>", " ", html))))
        space = page.get("space", {}).get("name") or page.get("_expandable", {}).get("space", "").split("/")[-1]
        return KnowledgeUnit(
            external_id=str(page["id"]), title=page["title"], doc_type=doc_type, sections=secs,
            updated_at=page["version"]["when"][:10], created_at=page.get("history", {}).get("createdDate", page["version"]["when"])[:10],
            owner_email=page["version"].get("by", {}).get("email"), author_email=page.get("history", {}).get("createdBy", {}).get("email"),
            country=country, version=str(page["version"]["number"]),
            location=f"Confluence › {space} › " + " › ".join(a["title"] for a in page.get("ancestors", [])),
            url=(page.get("_links", {}).get("base", "") + page.get("_links", {}).get("webui", "")) or "",
        )
