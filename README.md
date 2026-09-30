> Team working doc: https://docs.google.com/document/d/1Sd3y1srWgh8ZwH282dtvsXq3oxlC1VOh6FKil8sWyVY/edit?usp=sharing

# Grounded · SD Worx knowledge assistant (first iteration)

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

1. *Notice period, Belgium, 5 years* → answer from policy v2; review shows the 2021 v1 (owner left) as outdated and a personal copy as duplicate.
2. *Guaranteed salary during sick leave, Belgium* → owned manual wins over a fresher CTO Teams message saying 60 days; legal email confirms; conflict shown side by side with the reason.
3. *Vacation days, Netherlands* → Dutch policy answers; Belgian policy shown under **Wrong scope**.
4. *Meal voucher face value for Colruyt + provider after the switch* → part one answered from a procedure, part two only from an open Jira ticket, so it is marked informal and routed to Nadia and Amira.
5. *What did we decide about holiday pay for Delhaize* → the meeting's Decision line, backed by the related ticket.
6. *Notice period, France* → no evidence; closest experts listed with why.
7. **Add knowledge** (top bar) as Nadia: title "Decision: Colruyt meal voucher provider from 2027", type *Meeting decision*,
   country Belgium, client Colruyt, topics *Voucher providers* + *Meal vouchers*, text
   "Colruyt procurement confirmed Pluxee as the meal voucher provider from 1 January 2027. eBlox export format PLX-2 must be
   configured for the Colruyt client before the December 2026 run." Then re-ask question 4: part two is now a grounded
   answer from the new decision and the ticket drops to *Earlier*.

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
