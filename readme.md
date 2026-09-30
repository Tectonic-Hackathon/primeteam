# Knowledge Trust — local hackathon prototype

[Team working document](https://docs.google.com/document/d/1Sd3y1srWgh8ZwH282dtvsXq3oxlC1VOh6FKil8sWyVY/edit?usp=sharing)

A synthetic, local proof of concept for the SD Worx knowledge trust challenge. It answers a fictional payroll handover question with exact source excerpts, shows applicable scope and exclusions, surfaces conflicts and missing knowledge, and suggests an expert using recorded activity. **No source in this app is real SD Worx policy, employee data, or customer information.**

The source requirements are in [`SDWorx challenge/sdworx-knowledge-trust-requirements.md`](SDWorx%20challenge/sdworx-knowledge-trust-requirements.md).

## Run locally

Requirements: Python 3.11+, Node.js 20+, npm. Docker and API keys are not needed.

```bash
python3 -m venv .venv
.venv/bin/pip install -r api/requirements.txt
cd web && npm install --cache ../.npm-cache && cd ..
```

Start the API in one terminal:

```bash
.venv/bin/uvicorn main:app --app-dir api --host 127.0.0.1 --port 8000
```

Start the UI in another:

```bash
cd web
npm run dev
```

Open **http://127.0.0.1:5173/**. The API seeds 14 synthetic Atlas sources plus the 8 source payroll cutoff dataset automatically into `data/knowledge-trust.sqlite3` on first launch. An existing database from before the dataset receives the payroll cutoff sources on the next start. No demo credentials are needed. The sidebar's **Viewing as** control switches between simulated Employee and Knowledge steward roles. The steward can import files through the Source library. These are demonstration roles, not authentication.

Optional environment variables are listed in [`.env.example`](.env.example). `DATABASE_PATH` changes the SQLite file path. `VITE_API_URL` changes the UI's API base URL. The default ports are 8000 and 5173. A `.env` file is not required; export variables in your shell if you override them.

## Exact demo path

1. Open the UI. The Belgium question is prefilled. Keep **Belgium**, **Pay**, **Atlas**, **Project Atlas**, and **2026-09-30**; click **Find trusted answer**.
2. Point to the three verbatim claims and their `[E1]`–`[E3]` links. The checklist step is **conflicted**; the client-facing completion note is **missing**.
3. Open `[E1]`. Show the exact excerpt, section/line, owner, version, scope, effective date, and approval status. Click **Open stored original** to see the locally stored text with the cited excerpt highlighted.
4. Open **For review**. Show the unapproved Teams message and draft meeting proposal conflicting with the approved procedure, the near duplicate, superseded older version, and missing trust signals.
5. Return to **Answer & evidence**. Show Maya Vermeer as a suggested contact, with the linked procedure, ticket, and consultation activity. Her rank is a suggestion, not an authority claim.
6. Open **Retrieval details and exclusions**. Show why the France-only procedure and expired Belgium version were excluded.
7. Click **France handover**, then **Find trusted answer**. Only the France transfer register evidence appears as an answer. Belgium-only records do not become applicable.
8. Optionally switch to **Knowledge steward**, open **Source library**, and import a small `.md`, `.txt`, `.json`, `.eml`, or `.pdf` file. It remains a draft. Refresh the page to see it persists.

## Payroll cutoff demo dataset

A second synthetic topic lives in [`api/datasets/payroll_cutoff/`](api/datasets/payroll_cutoff/): when must payroll changes reach SD Worx before payday?

| Source | Status | Role in the demo |
|---|---|---|
| `be-cutoff-v3` | approved | Correct Belgian procedure: 5 working days, owner Lotte Vermeulen |
| `be-cutoff-v1` | superseded | Old version: 3 days, owner has left |
| `be-cutoff-quick-guide` | unknown | Near duplicate without owner or date: 4 days |
| `be-client-service-faq` | approved by another team | Conflict: 2 days and free correction runs |
| `nl-cutoff` | approved | Other country: 7 days |
| `be-knowledge-governance` | approved | Which source leads and who decides |
| `teams-be-consultants` | chat | The owner says the FAQ is wrong |
| `teams-fr-consultants` | chat | The only place the French deadline (6 days) exists |

`manifest.json` holds the metadata, the cited spans, relations, people and expert activity; `sources/` holds the stored originals. `demo_questions.json` has 9 questions (two per inspiration area: Trust, Detect, Connect, Capture, plus a scope check and a no answer case). They appear in the UI as **Payroll cutoff demo** buttons with a talking point, and `api/tests/test_payroll_cutoff.py` checks each expected result.

Cutoff questions get their own topic in the planner. Each part of the question (deadline, correction run, exceptions, contact person) is checked separately and marked **conflicted** when another applicable source states a different value. A country without an approved source gets a **Missing knowledge** item and the expert who answered in chat. Review items and general question experts are limited to sources retrieved for the question, so the Atlas and payroll demos do not mix.

Suggested 3 minute path: **Belgian deadline** → **Who decides?** → **French deadline** → **German deadline**.

## Architecture

```text
React / Vite UI
     │ HTTP, structured JSON
FastAPI: query planning → vector + FTS5 retrieval → scope/lifecycle rules
     │                                  ↓
     └──────────── claim validation ← candidate grouping / conflict checks
                                         │
SQLite: original blobs, source metadata, spans, vectors, FTS5, relations,
        expert activity, knowledge entities/edges, query runs, claims, audit events
```

The API creates up to four bounded query reformulations. Retrieval combines a local 256-dimensional concept-hash vector with SQLite FTS5 and lexical overlap. It applies the selected demo role, country, domain, client/project, and requested date before a source can support a claim. Approved, owned, effective sources may produce **verbatim** claim sentences; unapproved chats, emails, meetings, notes, and tickets remain candidates for review or expert activity. The API stores every claim-to-span link under the query run. Originals and vectors persist in SQLite; the vector/FTS index can be rebuilt from source spans.

The answer path is deterministic and needs no LLM key. It is deliberately conservative: it can show supported source sentences for other questions, but the explicit component and contradiction checks are built around the seeded handover topic. It is **not evidence that arbitrary questions are answered correctly**. The vector index is lightweight and should not be described as production semantic search.

### API

`GET /api/health`, `GET /api/sources`, `GET /api/sources/{id}`, `GET /api/sources/{id}/content`, `GET /api/sources/{id}/original`, `GET /api/evidence/{span_id}`, `GET /api/review-items`, `POST /api/query`, `POST /api/sources/import`, and `POST /api/index/rebuild` are available at `http://127.0.0.1:8000/docs`.

Use `X-Demo-Role: employee` or `X-Demo-Role: steward` to simulate the role on API requests. The default is employee. The source list, detail, evidence, original, query, and expert activity endpoints all enforce that simulated role server-side. `original` also accepts `?role=` so ordinary browser links can open a stored source. This role switch is intentionally user-controllable and is **not** production access control.

Imports require steward role, a unique source ID, title, type, country, domain, and a supported file. Files are capped at 2 MB; unsupported, empty, and unextractable files return clear errors. Uploads stay in draft status and cannot override an approved procedure. Normalized identical text is recorded as an exact-duplicate relation. PDF text extraction preserves page/line; text files preserve line; structured JSON `messages` preserve message ID and timestamp. Rebuild with:

```bash
curl -X POST -H 'X-Demo-Role: steward' http://127.0.0.1:8000/api/index/rebuild
```

## Verification

```bash
PYTHONPATH=api .venv/bin/pytest -q api/tests
cd web && npm run build
```

The tests cover claim/citation mapping, country and client scope, effective dates, conflicts, near duplicates, missing components, expert support, ACL checks, injection text, PDF originals, draft import, and index rebuild. The main browser journey was also checked at desktop and a 390px mobile viewport.

To reseed only this generated demo database, stop the API, remove `data/knowledge-trust.sqlite3`, and restart it. Keep that file if you want imported sources and query audit history to persist.

## Boundaries and next steps

- No Microsoft Graph, Teams, Outlook, Jira, SSO, or cloud connection is active. Seeded records only imitate their formats.
- No general LLM answer synthesis, production embedding model, or verified arbitrary-query correctness. The deterministic path favors abstention.
- Meeting transcript content is seeded as a draft and shown for review. Human approval, correction, version promotion, and reindexing are next-phase work.
- The role selector is a demo ACL exercise, not secure authentication or tenant isolation. Do not put real confidential material into this app.
- Upload extraction is intentionally small and line-oriented. Complex PDFs and structured document hierarchies need a richer ingestion pipeline.
- Aikido audit was not available in this local workspace; no audit result or submission readiness is claimed.

Once the local user journey and data rules are accepted, the storage, index, identity, and connector interfaces can be replaced or extended for Google Cloud without changing the evidence contract.
