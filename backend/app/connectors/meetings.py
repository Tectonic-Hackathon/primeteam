"""Meeting transcripts → summary, decisions, actions, people. Live: Microsoft Graph online meeting transcripts
(OnlineMeetingTranscript.Read.All). Also reachable as a webhook so any recorder/meeting agent can push a transcript."""
import os
import re
from .base import Connector, KnowledgeUnit, sentences
from . import msgraph

_DECISION = re.compile(r"^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?(?:[\w .'-]+:\s*)?(?:decision|decided|we agreed|agreed)\s*[:\-–]?\s*(.+)$", re.I)
_ACTION = re.compile(r"^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?(?:[\w .'-]+:\s*)?(?:action|todo|to do|next step)\s*(?:\(([^)]+)\))?\s*[:\-–]\s*(.+)$", re.I)
_SPEAKER = re.compile(r"^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?([A-Z][\w .'-]+?):\s*(.+)$")


def extract(transcript: str) -> dict:
    """Rule-based extraction. Swap for a small local model later behind the same signature."""
    decisions, actions, discussion, speakers = [], [], [], []
    for line in transcript.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _DECISION.match(line)
        if m:
            decisions.append("Decision: " + m.group(1).rstrip(".") + ".")
            continue
        m = _ACTION.match(line)
        if m:
            owner = f" ({m.group(1)})" if m.group(1) else ""
            actions.append(f"Action{owner}: " + m.group(2).rstrip(".") + ".")
            continue
        m = _SPEAKER.match(line)
        if m:
            if m.group(1) not in speakers:
                speakers.append(m.group(1))
            discussion.append(m.group(2))
        else:
            discussion.append(line)
    summary = sentences(" ".join(discussion))[:3]
    return {"summary": summary, "decisions": decisions, "actions": actions, "speakers": speakers}


def unit_from_transcript(meeting_id: str, title: str, transcript: str, when: str, organizer_email: str | None,
                         attendee_emails: list[str], location: str = "", url: str = "", client: str | None = None,
                         country: str | None = None) -> KnowledgeUnit:
    ex = extract(transcript)
    secs = []
    if ex["decisions"]:
        secs.append(("Decisions", ex["decisions"]))
    if ex["actions"]:
        secs.append(("Actions", ex["actions"]))
    if ex["summary"]:
        secs.append(("Summary", ex["summary"]))
    return KnowledgeUnit(
        external_id=meeting_id, title=f"Meeting notes – {title}", doc_type="meeting", sections=secs,
        updated_at=when[:10], created_at=when[:10], owner_email=organizer_email, author_email=organizer_email,
        attendee_emails=attendee_emails, client=client, country=country,
        location=location or f"Teams meeting › {title} › {when[:16].replace('T', ' ')}", url=url,
    )


class MeetingsConnector(Connector):
    name = "meetings"
    label = "Meetings"
    source_system = "Meeting Recorder"
    description = "Recorded meetings: transcript in, summary + decisions + actions + people out (Graph transcripts or webhook)."
    id_prefix = "MT"
    required_env = ("MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET", "MEETINGS_ORGANIZER_IDS")
    docs_url = "https://learn.microsoft.com/graph/api/onlinemeeting-list-transcripts"

    def fetch_live(self, since):
        units = []
        for user in os.environ["MEETINGS_ORGANIZER_IDS"].split(","):
            for mtg in msgraph.paged(f"/users/{user.strip()}/onlineMeetings"):
                for tr in msgraph.paged(f"/users/{user.strip()}/onlineMeetings/{mtg['id']}/transcripts"):
                    vtt = msgraph.get(f"/users/{user.strip()}/onlineMeetings/{mtg['id']}/transcripts/{tr['id']}/content", {"$format": "text/vtt"}, raw=True)
                    text = "\n".join(l for l in vtt.splitlines() if l and "-->" not in l and l != "WEBVTT")
                    text = re.sub(r"<v ([^>]+)>", r"\1: ", text).replace("</v>", "")
                    units.append(unit_from_transcript(
                        tr["id"], mtg.get("subject", "Meeting"), text, tr["createdDateTime"],
                        (mtg.get("participants", {}).get("organizer", {}).get("upn")),
                        [a.get("upn") for a in mtg.get("participants", {}).get("attendees", []) if a.get("upn")],
                        url=mtg.get("joinWebUrl", "")))
        return units

    def parse_fixture(self, item):
        return unit_from_transcript(item["id"], item["subject"], item["transcript"], item["createdDateTime"],
                                    item.get("organizer"), item.get("attendees", []), item.get("location", ""), item.get("joinWebUrl", ""),
                                    item.get("client"), item.get("country"))
