> Team working doc: https://docs.google.com/document/d/1Sd3y1srWgh8ZwH282dtvsXq3oxlC1VOh6FKil8sWyVY/edit?usp=sharing

# Grounded · SD Worx knowledge assistant

**Hackathon submission write-up: [SUBMISSION.md](SUBMISSION.md)**

One question in, one grounded answer out: every sentence cites a passage (document → section → line),
every passage carries six trust signals, and everything that conflicts, duplicates, is outdated or
belongs to another country is pushed to a **For review** tab instead of silently blended in.
When the knowledge base cannot answer, the knowledge graph names the people most likely to know.

## Run

```bash
./run.sh            # starts colima if needed, Postgres+pgvector and Ollama containers, seeds, serves
open http://localhost:8000
```

Third parties run only as containers (see `docker-compose.yml`): `pgvector/pgvector:pg16` on port 5433 and
`ollama/ollama` on port 11435 with the small `nomic-embed-text` model (274MB) for embeddings.
No paid API is used. If Ollama is unavailable the app falls back to offline hashed embeddings automatically.

Reseed after editing the corpus: `cd backend && ../.venv/bin/python seed/seed.py`

## What is in the box

| Path | Purpose |
|---|---|
| `backend/app/pipeline/context.py` | Resolve country, client, domain, intent, topics from the question (or the asker's profile) |
| `backend/app/pipeline/planner.py` | Split into sub-questions, generate rewrites per topic |
| `backend/app/pipeline/retrieval.py` | Hybrid search: pgvector cosine + Postgres full-text, reciprocal rank fusion, intent boosts |
| `backend/app/pipeline/trust.py` | Freshness, owner, scope, authority, channel, supersession → one explainable score |
| `backend/app/pipeline/conflicts.py` | Cluster same-topic passages across documents; detect duplicates and contradicting facts |
| `backend/app/pipeline/experts.py` | Reputation per person per topic per country from graph edges, seniority only as a tie-breaker |
| `backend/app/pipeline/consolidate.py` | Build the answer with E1..En citations, statuses, confidence, review buckets |
| `backend/seed/corpus.py` | Synthetic corpus with every failure mode planted on purpose |
| `backend/app/static/` | UI: Answer / For review / How it was answered, source and person detail popups, document viewer with highlighted lines |

## Demo script

The corpus merges three fictional datasets: our own HR/payroll set, the team's **payroll cutoff** set (branch `demo-dataset`)
and the team's **parental leave / Northstar** set (branch `demo-dataset-2`, `SDWorx_Simple_Trust_Demo`). The example chips on the
landing page run these, in order:

| Question | What it shows |
|---|---|
| Laura's contractual salary at 80% or 100% during 1/5 parental leave? | Country and client resolved from the employee (Northstar, Belgium). Answer 80% from guide v3. Issues: the guide's own retained old paragraph (100%), Client Service email (100%, says itself it relies on old material), legacy 2022 procedure whose owner left, Dutch document out of scope. |
| How much public parental-leave allowance will Laura receive? | Refuses: the guide states explicitly that it does not determine the allowance. Nothing is claimed; Amélie Dubois (benefits specialist, from the expertise directory) is the person to ask. |
| Deadline for payroll changes, Belgian client? | 5 working days from procedure v3. Issues: Client Service FAQ says 2 days (conflict, procedure leads per governance policy), quick guide without owner or date (unofficial, looks like a copy saying 4 days), v1 from 2021 (outdated). Lotte Vermeulen is the expert. |
| Payroll change deadline for French clients? | Only a Teams message from Julien Moreau answers. Marked informal, with an *Undocumented* issue: capture it as a note in one click, or ask Julien to write the procedure. |
| Multiple versions of the Belgian cutoff procedure? | Yes: v1 (2021) still exists and is excluded; v3 is used. |
| Who can I ask about the Belgian cutoff rule? | Contact line from v3 and Lotte Vermeulen as expert. Marc Peeters (left) is never suggested. |
| The FAQ and the procedure disagree, who decides? | Governance policy: the procedure owner decides. Eva Claes and Lotte Vermeulen suggested. |
| Payroll change deadline for Dutch payrolls? | 7 working days from the Dutch procedure; Belgian sources shown as wrong country. |
| Payroll change deadline in Germany? | Nothing known, nothing invented. Closest expertise shown with a note that no German specialist exists. |
| Guaranteed salary during sick leave, Belgium (our set) | Owned manual beats a fresher CTO Teams message (60 days vs 30); legal email confirms; manual flagged *Review overdue*. |

More of our own scenarios (notice period versions and duplicate copy, Colruyt two-part question, Delhaize meeting decision,
Siemens 13th month) are under *More examples*. Adding knowledge live: **Add knowledge** → write a note, or *Connected sources* → Sync.

Known gaps: "Is a correction run free?" currently leads with the deadline sentence of the right procedure instead of its
correction-run sentence (the conflict itself is detected); "Can I trust the quick guide?" has no country in the question and the
scope inference is not decisive yet. Both are left out of the example chips.

## Ranking rules worth saying out loud in the pitch

- When several formal, owned sources answer the same question, the **latest** one wins (the brief's rule). Tickets, chats and
  emails never win on recency alone; they surface as *Informal source* with people to confirm.
- A conflict is two same-topic passages from different documents that state a different value for the same unit
  (days, weeks, %, €). The kept one is explained: owner, channel, expertise, recency.
- Reputation is per person per topic per country; seniority is capped at a small multiplier.
- The answer text is verbatim from cited passages, so there is nothing to hallucinate.

## UI principles

- Progressive disclosure: one bold answer sentence first, detail below it, sources collapsed, three example questions
  with a "more" link. Related passages are one-line references, not quotes.
- One number per source: **confidence** (match to the question × trust in the source). The eye icon opens the breakdown:
  the six trust signals with plain-language notes, the exact passage, and a jump to the document at the cited line.
- Every person has an eye icon too: it opens their credibility on this topic, how the score is built (owning and writing
  count most, editing and answering next, attending least; recency and country scope weigh in; seniority is a tie-breaker)
  and their full track record. A source's details end with "Who stands behind it": who owns, wrote, edited or reviewed it.
- When there is no reliable answer, the side card switches to **"No reliable answer, ask"** with the people most likely to
  know and an *Ask* button that drafts the email. When the answer rests on a disputed or informal source the card reads
  **"Worth confirming with"**. Country specialists are preferred; if none exist the card says so and shows the closest expertise.

## Where knowledge comes from

`backend/app/connectors/` holds one connector per source with the real API request shapes: SharePoint, Teams, Outlook and
Meetings via Microsoft Graph (client-credentials app registration), Jira and Confluence via Atlassian REST. A connector is
**live** when its environment variables are set and otherwise runs in **demo** mode on `fixtures/<name>.json`, which mimic the
raw API payloads so the same parsers run. Any other system can push directly:

```
POST /api/ingest/documents          bulk documents (sections = [[heading, [sentences]]])
POST /api/ingest/meeting            a transcript; decisions/actions/summary/people are extracted
POST /api/ingest/webhook/{name}     change notification → delta sync (echoes Graph validationToken)
POST /api/connectors/{name}/sync    manual sync, ?since=YYYY-MM-DD, ?full=true also archives vanished docs
```

Live mode env vars: `MS_TENANT_ID MS_CLIENT_ID MS_CLIENT_SECRET` plus `SHAREPOINT_DRIVE_ID`, `TEAMS_TEAM_ID TEAMS_CHANNEL_IDS`,
`OUTLOOK_MAILBOXES`, `MEETINGS_ORGANIZER_IDS`; `ATLASSIAN_URL ATLASSIAN_EMAIL ATLASSIAN_TOKEN` plus `JIRA_JQL`, `CONFLUENCE_SPACES`.

## How memory stays fresh

1. **Delta syncs** run for every connector every `SYNC_INTERVAL_MINUTES` (default 30) and on webhook, fetching only what
   changed since the last successful run. A `full=true` sync also archives documents that disappeared from the source.
2. **Change detection.** Each document carries a content hash. Unchanged: only `last_seen_at` is touched, nothing is
   re-embedded. Changed: a row is added to `document_versions` with a fact-level change summary ("Cap: €98.000 → €102.000"),
   an *edited* edge is recorded for the modifier (feeding their reputation), open update tasks on the document are closed,
   and only the sections whose text changed are re-embedded.
3. **Supersession.** A new document whose title stem matches an older one for the same country supersedes it automatically;
   the old one drops out of answers and shows up under *Outdated* with a pointer to the successor.
4. **Review periods.** Owned documents have a review period per type (1.2 × the trust half-life). The freshness sweep, run
   after each scheduled sync, opens a *confirm still valid* task for the owner when a document passes its period, and a
   *reassign owner* task when the owner has left. Owners close them by editing (picked up by sync) or by clicking
   **Confirm still valid**, which sets `validated_at`; trust uses the later of edit and confirmation.
5. **Fixes from the Issues tab** (retract, archive, request update, confirm valid) change document status immediately and apply
   to everyone's next answer; every fix has undo. Informal sources (chat, email, tickets, meetings) are never asked for review;
   they decay quickly by design.
6. **Overview**: `GET /api/freshness` reports documents touched in 180 days, overdue reviews, open tasks and versions; the
   *Connected sources* panel shows it with a *Run freshness sweep* button.

## Not in this iteration

Live credentials for the connectors (they run on demo fixtures here), text extraction for .docx/.pdf in SharePoint,
an LLM writer for the final prose (the consolidator is deterministic so grounding is guaranteed), and authentication.
The `LLM_BACKEND` setting is reserved for plugging a small local model into the write-up step.
