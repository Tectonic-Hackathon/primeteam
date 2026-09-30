"""Teams channel messages via Microsoft Graph (ChannelMessage.Read.All). Every message with substance becomes a chat unit;
the trust model already ranks chat below owned documents, so this is safe to ingest broadly."""
import os
import re
from .base import Connector, KnowledgeUnit, sentences
from . import msgraph


class TeamsConnector(Connector):
    name = "teams"
    label = "Teams"
    source_system = "Teams"
    description = "Channel messages where rules get announced or answered before any document is updated (Graph channel messages)."
    id_prefix = "TM"
    required_env = ("MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET", "TEAMS_TEAM_ID", "TEAMS_CHANNEL_IDS")
    docs_url = "https://learn.microsoft.com/graph/api/channel-list-messages"

    def fetch_live(self, since):
        team = os.environ["TEAMS_TEAM_ID"]
        units = []
        for ch in os.environ["TEAMS_CHANNEL_IDS"].split(","):
            for m in msgraph.paged(f"/teams/{team}/channels/{ch.strip()}/messages", {"$top": 50}):
                u = self.parse_fixture({**m, "channelName": ch.strip()})
                if u:
                    units.append(u)
        return units

    def parse_fixture(self, m):
        text = re.sub(r"<[^>]+>", " ", m.get("body", {}).get("content", "")).strip()
        if len(text) < 60:
            return None
        user = (m.get("from") or {}).get("user") or {}
        when = m["lastModifiedDateTime"][:10] if m.get("lastModifiedDateTime") else m["createdDateTime"][:10]
        channel = m.get("channelName", "channel")
        return KnowledgeUnit(
            external_id=m["id"], title=f"Teams message in #{channel}", doc_type="chat", sections=[("Message", sentences(text))],
            updated_at=when, created_at=m["createdDateTime"][:10], author_email=user.get("email") or user.get("userIdentityType"),
            location=f"Teams › #{channel} › {m['createdDateTime'][:16].replace('T', ' ')}", url=m.get("webUrl", ""),
        )

    def fetch_demo(self):
        return [u for u in super().fetch_demo() if u]
