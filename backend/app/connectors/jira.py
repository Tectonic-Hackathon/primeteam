"""Jira Cloud issues via REST API v3 search (JQL)."""
import os
import httpx
from .base import Connector, KnowledgeUnit, sentences


def _adf_text(node) -> str:
    """Flatten Atlassian Document Format to text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    out = []
    if node.get("type") == "text":
        out.append(node.get("text", ""))
    for c in node.get("content", []) or []:
        out.append(_adf_text(c))
    return " ".join(x for x in out if x)


class JiraConnector(Connector):
    name = "jira"
    label = "Jira"
    source_system = "Jira"
    description = "Tickets and their status, so open work is visible next to documented rules (REST API v3, JQL search)."
    id_prefix = "JR"
    required_env = ("ATLASSIAN_URL", "ATLASSIAN_EMAIL", "ATLASSIAN_TOKEN", "JIRA_JQL")
    docs_url = "https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/"

    def fetch_live(self, since):
        base = os.environ["ATLASSIAN_URL"].rstrip("/")
        jql = os.environ["JIRA_JQL"] + (f" AND updated >= '{since}'" if since else "")
        r = httpx.get(f"{base}/rest/api/3/search", auth=(os.environ["ATLASSIAN_EMAIL"], os.environ["ATLASSIAN_TOKEN"]), timeout=60,
                      params={"jql": jql, "maxResults": 100, "fields": "summary,description,status,assignee,reporter,created,updated,labels,project"})
        r.raise_for_status()
        return [self.parse_fixture(i) for i in r.json().get("issues", [])]

    def parse_fixture(self, issue):
        f = issue["fields"]
        desc = f.get("description")
        text = _adf_text(desc) if isinstance(desc, dict) else (desc or "")
        labels = [l.lower() for l in f.get("labels", [])]
        country = next((l.upper() for l in labels if l.upper() in ("BE", "NL", "DE", "FR", "UK")), None)
        client = next((l.title() for l in labels if l.startswith("client-")), None)
        client = client.replace("Client-", "") if client else None
        status = f.get("status", {}).get("name", "")
        secs = [("Description", sentences(text))]
        if status:
            secs.append(("Status", [f"Status: {status}."]))
        return KnowledgeUnit(
            external_id=issue["key"], title=f"{issue['key']} – {f['summary']}", doc_type="ticket", sections=secs,
            updated_at=f["updated"][:10], created_at=f["created"][:10],
            owner_email=(f.get("assignee") or {}).get("emailAddress"), author_email=(f.get("reporter") or {}).get("emailAddress"),
            country=country, client=client, location=f"Jira › {f.get('project', {}).get('key', '')} › {issue['key']}",
            url=f"{os.getenv('ATLASSIAN_URL', 'https://sdworx.atlassian.net').rstrip('/')}/browse/{issue['key']}",
        )
