"""Shared mailbox via Microsoft Graph mail API (Mail.Read on the mailbox). Emails to a team alias such as
payroll-be@ often carry the real ruling from legal or a client."""
import os
import re
from .base import Connector, KnowledgeUnit, sentences
from . import msgraph


class OutlookConnector(Connector):
    name = "outlook"
    label = "Outlook"
    source_system = "Outlook"
    description = "Emails to team mailboxes, where rulings and client confirmations often live (Graph mail API)."
    id_prefix = "OL"
    required_env = ("MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET", "OUTLOOK_MAILBOXES")
    docs_url = "https://learn.microsoft.com/graph/api/user-list-messages"

    def fetch_live(self, since):
        units = []
        for mb in os.environ["OUTLOOK_MAILBOXES"].split(","):
            params = {"$top": 50, "$select": "id,subject,bodyPreview,body,from,toRecipients,receivedDateTime,webLink"}
            if since:
                params["$filter"] = f"receivedDateTime ge {since}T00:00:00Z"
            for m in msgraph.paged(f"/users/{mb.strip()}/messages", params):
                units.append(self.parse_fixture({**m, "mailbox": mb.strip()}))
        return units

    def parse_fixture(self, m):
        text = re.sub(r"<[^>]+>", " ", m.get("body", {}).get("content", "") or m.get("bodyPreview", ""))
        sender = (m.get("from") or {}).get("emailAddress", {})
        when = m["receivedDateTime"][:10]
        return KnowledgeUnit(
            external_id=m["id"], title=f"Email: {m['subject']}", doc_type="email", sections=[("Body", sentences(text))],
            updated_at=when, created_at=when, owner_email=sender.get("address"), author_email=sender.get("address"),
            location=f"Outlook › {m.get('mailbox', 'mailbox')} › {m['receivedDateTime'][:16].replace('T', ' ')}", url=m.get("webLink", ""),
        )
