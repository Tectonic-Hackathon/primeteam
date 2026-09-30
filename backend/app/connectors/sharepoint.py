"""SharePoint document libraries via Microsoft Graph drives API.
Live: lists files in a drive, downloads text-bearing files, maps library folder to doc_type/country by convention."""
import os
import re
from .base import Connector, KnowledgeUnit, sentences
from . import msgraph


class SharePointConnector(Connector):
    name = "sharepoint"
    label = "SharePoint"
    source_system = "SharePoint"
    description = "Policies, procedures and checklists from document libraries (Microsoft Graph drives API)."
    id_prefix = "SP"
    required_env = ("MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET", "SHAREPOINT_DRIVE_ID")
    docs_url = "https://learn.microsoft.com/graph/api/driveitem-list-children"

    def fetch_live(self, since):
        drive = os.environ["SHAREPOINT_DRIVE_ID"]
        params = {"$select": "id,name,webUrl,lastModifiedDateTime,createdDateTime,createdBy,lastModifiedBy,parentReference,file"}
        if since:
            params["$filter"] = f"lastModifiedDateTime ge {since}T00:00:00Z"
        units = []
        for item in msgraph.paged(f"/drives/{drive}/root/search(q='')", params):
            if "file" not in item or not item["name"].lower().endswith((".txt", ".md", ".csv")):
                continue  # docx/pdf need a text extraction step; out of scope for the first iteration
            body = msgraph.get(f"/drives/{drive}/items/{item['id']}/content", raw=True)
            units.append(self._unit(item, body))
        return units

    def parse_fixture(self, item):
        return self._unit(item, item["content"])

    def _unit(self, item, body: str) -> KnowledgeUnit:
        folder = (item.get("parentReference", {}).get("path") or "").split("/")
        doc_type = next((f.lower().rstrip("s") for f in folder if f.lower() in ("policies", "procedures", "checklists", "manuals")), "wiki")
        country = next((f for f in folder if f in ("BE", "NL", "DE", "FR", "UK")), None)
        title = re.sub(r"\.(txt|md|csv|docx)$", "", item["name"])
        secs = []
        for block in re.split(r"\n(?=## )", body.strip()):
            lines = block.strip().split("\n", 1)
            heading = lines[0].lstrip("# ").strip() if lines[0].startswith("##") else "Content"
            text = lines[1] if len(lines) > 1 else (lines[0] if heading == "Content" else "")
            if text.strip():
                secs.append((heading, sentences(text)))
        return KnowledgeUnit(
            external_id=item["id"], title=title, doc_type=doc_type, sections=secs,
            updated_at=item["lastModifiedDateTime"][:10], created_at=(item.get("createdDateTime") or item["lastModifiedDateTime"])[:10],
            owner_email=(item.get("lastModifiedBy") or {}).get("user", {}).get("email"),
            author_email=(item.get("createdBy") or {}).get("user", {}).get("email"),
            country=country, location="SharePoint › " + " › ".join(f for f in folder if f and f != "root:"), url=item.get("webUrl", ""),
        )
