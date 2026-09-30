# Grounded — Knowledge you can trust · Tectonic Hackathon submission (SD Worx challenge)

**Team primeteam** · Proof of concept · Repository root, run with `./run.sh`

## The problem

Knowledge at SD Worx is spread over documents, chats, emails, tickets, meetings and people, across 30 countries and dozens of
products. The information usually exists. Confidence does not: which source is current, which applies to this country and client,
what disagrees with what, what is missing, and who actually knows.

## What Grounded does

One question in. One answer out, with:

| Challenge aspiration | How Grounded answers it |
|---|---|
| **Trust** – is this reliable? | Every sentence is a verbatim passage cited to document → section → line. Each source carries one **confidence** number (match × trust) and six explainable trust signals: freshness, owner, scope, authority, channel, supersession. |
| **Capture** – knowledge beyond inboxes and silos | Connectors for SharePoint, Confluence, Jira, Teams, Outlook and meeting transcripts (decisions/actions extracted), a push API, and an **Add knowledge** form. Informal answers can be captured as an owned note in one click. |
| **Detect** – conflicting, duplicated, missing, outdated | An **Issues** tab lists conflicts (with the values side by side and why one won), duplicates, outdated versions, wrong-country hits, unofficial documents, undocumented answers and overdue reviews. Each issue has fix actions that change the knowledge base immediately, with undo. |
| **Connect** – find the right expertise | A knowledge graph of people, documents and topics gives **reputation per person per topic per country**. Seniority is only a tie-breaker. When nothing reliable exists the answer says so and names who to ask, with their track record. |

Two behaviours the demo datasets test explicitly: the system **resolves a conflict** (owned procedure beats a fresher chat or FAQ)
and the system **refuses** when documents state they do not determine the answer, routing to the listed expert instead of guessing.

## Architecture (PoC)

```
Sources ──connectors/push/webhook──▶ Postgres + pgvector ◀── seed corpus (3 fictional datasets)
                                        │  documents · chunks(embeddings) · people · edges · versions · tasks
Question ─▶ context ─▶ planner ─▶ hybrid retrieval ─▶ trust scoring ─▶ conflict/duplicate/scope analysis ─▶ consolidation ─▶ UI
              │           │            │                   │                    │                             │
          country,    sub-questions  pgvector cosine    six signals,       clusters same-topic passages,   verbatim lead sentence,
          client,     + rewrites     + full-text,       review periods     fact comparison, governance      E1..En, issues, experts
          intent,                    rank fusion                            rules
          topics
```

- **Backend**: Python 3.11, FastAPI, psycopg + pgvector. **Embeddings**: `nomic-embed-text` in a local Ollama container (274 MB);
  offline hashed fallback so the demo never depends on a network model. **UI**: vanilla JS, no build step.
  All third parties run as containers (`docker-compose.yml`); no paid API is used anywhere.
- **Deterministic by design**: the final text is composed only of cited passages, so nothing can be hallucinated. An LLM writer
  can be added behind the same interface later; the trust and detection logic does not depend on one.

## Technical implementation

**Context resolution** (`pipeline/context.py`). Country, client, domain, intent and topics from keyword taxonomies; client from a
client list or from an employee directory ("Laura" → Northstar → Belgium). If the question names no country, it is inferred from
the most relevant documents when they agree.

**Planning** (`pipeline/planner.py`). Splits multi-part questions into sub-questions (each checked independently, which is what makes
gap detection possible) and adds topic-specific rewrites for recall.

**Retrieval** (`pipeline/retrieval.py`). pgvector cosine plus Postgres full-text, fused with reciprocal rank fusion. Relevance =
0.45·vector + 0.35·lexical + 0.2·topic match, with small intent boosts (decisions for "what did we decide", contact sections for
"who can I ask", passages stating the asked fact for yes/no questions).

**Trust** (`pipeline/trust.py`). `trust = 0.30·freshness + 0.20·owner + 0.15·authority + 0.15·channel + 0.20·supersession`, masked to 0
when out of scope. Freshness decays with a half-life per document type (policy 720 d … chat 90 d) from the later of last edit and
owner confirmation. Channel: policy > procedure > manual > checklist > wiki > meeting > ticket > email > chat. Documents without owner
and date are **unofficial** and never evidence (knowledge governance rule).

**Detection** (`pipeline/conflicts.py`). Same-topic, same-country passages from different documents are clustered (embedding
similarity, token overlap, or a shared fact key). Facts are extracted per unit (days, weeks, %, €) plus keyword facts (free vs
charged, no exceptions vs some). Different values for the same unit = conflict; near-identical text = duplicate. Questions and
reported speech never count as claims; differing conditions (5 vs 7 years of service) mean different cases, not a conflict.
Contradictions inside one document are found too. Winner rule, from the brief: the latest source **with an owner, a date and the
right scope** wins; official procedures lead over notes and FAQs; tickets, chats and emails never win on recency alone.

**Expertise** (`pipeline/experts.py`). Reputation(person, topics, country) = Σ over graph edges (owns, authored, edited, answered,
consulted, reviewed, listed, attended) of weight × recency decay × country scope × channel weight of the document, then a
saturating normalisation to 0–100. Seniority multiplies by at most 1.15. Country specialists are preferred; otherwise the UI says
none exist and shows the closest expertise.

**Consolidation** (`pipeline/consolidate.py`). Per sub-question: status answered / contested / informal / partial / missing; the lead
sentence is the passage sentence that best matches the question; confirming, earlier and related passages become one-line
references; a passage that explicitly says "does not determine" forces a refusal with the right experts.

**Freshness lifecycle** (`connectors/ingest.py`, `freshness.py`). Delta syncs every 30 min and on webhook; content hashing skips
unchanged documents; changed ones get a version row with a fact-level change summary ("Cap: €98.000 → €102.000"), an *edited* edge for
the modifier and re-embedding of changed sections only; same title stem → automatic supersession; review periods per type open
*confirm still valid* tasks for owners and *reassign owner* tasks when owners leave.

**Fix actions** (`POST /api/review/action`). retract, archive, request_update (creates a task, drafts the email), validate, restore.
Status changes apply to everyone's next answer.

## PoC boundaries

Fictional data only. Connectors run on fixture payloads shaped like the real APIs; live mode needs a Microsoft Graph app registration
and Atlassian tokens. Rule-based taxonomy and extraction instead of an LLM, which keeps the demo explainable but limits recall on
unseen phrasing. No authentication. Two example questions were left out of the chips because the passage choice is not yet right
(see README, *Known gaps*).

## Run it

```bash
./run.sh          # colima, Postgres+pgvector and Ollama containers, model pull, seed, serve
open http://localhost:8000
```
