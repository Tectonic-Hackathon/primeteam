# SD Worx Knowledge Trust — product and build requirements

**Version:** 1.0 · 30 September 2026
**Purpose:** Hand this file to Codex in VS Code to build a working hackathon proof of concept.
**Core promise:** Help an employee move from “I found something” to “I understand why I can rely on it.”

## 1. Build mandate

Build a professional web application that answers an employee's question using fragmented organisational knowledge. It must show the precise evidence behind each claim, decide which sources apply to the user's context, expose contradictions and gaps, and identify an appropriate expert when the evidence is insufficient.

The application must be runnable and demonstrable with **synthetic data**. It must not require access to SD Worx internal systems, real employee messages, customer data, or live Microsoft/Jira credentials. Design integration interfaces so these can be added later with authorisation.

### Instructions to the implementing Codex agent

1. Inspect the repository, its `AGENTS.md`, current stack, scripts, and tests before changing code. Preserve working conventions. If the repository is empty, use the default stack in section 12.
2. Build the P0 scope first and get the complete demo journey running before adding P1 features. Do not replace working core functionality with architectural placeholders.
3. Keep the answer engine evidence constrained: a generated sentence cannot be presented as established fact without a source span. A model's confidence is not evidence.
4. Use synthetic, clearly labelled fixture data. Never imply that the demo contains actual SD Worx policy or production integrations.
5. Document the setup, environment variables, demo credentials if any, test command, architecture, known limitations, and the exact demo script in the README.
6. Run the relevant checks and manually verify the primary demo flow in a browser. Report what actually ran and any incomplete requirements.

## 2. Source of requirements and factual boundaries

The hackathon challenge asks for a **focused proof of concept** that makes organisational knowledge easier to find, trust, or share. It explicitly highlights reliability, recency, context, gaps, expertise, and visible trust. The challenge guide describes SD Worx as having **10,000+ employees, 100,000+ customers, and 6M+ payslips**, with payroll reach into more than 100 countries. Use **6M+**, not “6k,” when quoting the guide. These figures provide context; they are **not** system load targets for the hackathon build.

The other figures supplied in the team's design notes — 100+ payroll services, 30 local expertise areas, 20 own payroll engines, 17 HCM solutions, 17 WFM solutions, and 14 SAP solutions — have not been verified for this build. Keep them out of product claims and sample charts unless the team supplies a source. The architecture should support heterogeneous countries, teams, and systems without assuming those exact counts.

Sources for the challenge and visual direction:

- Tectonic Hackathon Participants Guide, SD Worx challenge, page 5 (supplied by the team).
- [Current SD Worx website](https://www.sdworx.com/en-en).
- [SD Worx 2026 brand update](https://www.sdworx.com/en-en/about-sd-worx/press/2026-06-25-new-look-sd-worx-introducing-brand-makes-work-work).

## 3. User and outcome

**Primary user:** an employee, such as a payroll consultant, who must answer a customer or internal question quickly and with justified confidence.
**Secondary user:** a source owner or knowledge steward who resolves outdated, duplicate, and conflicting information.
**Tertiary user:** a domain expert who can be contacted when documented knowledge is incomplete.

The user must be able to:

1. Ask one natural-language question and provide context, especially country, business area, customer/project if relevant, and the date for which the answer is needed.
2. See a readable answer with evidence IDs such as `[E1]`, `[E2]` attached to individual claims.
3. Open an evidence ID to see the exact source excerpt, location, owner, dates, scope, status, and original stored source.
4. See which evidence is current and applicable, which was excluded and why, and which parts remain unknown.
5. Open a **For review** tab for conflicts, duplicates, outdated sources, missing owners, and missing knowledge.
6. Find a suggested expert with an explanation grounded in recent, permitted topic-related activity.

## 4. Scope and priorities

### P0 — must work for the hackathon demonstration

- Upload or seed PDFs, Markdown/text documents, and structured demo records representing Teams chats, email, meeting transcript/decision, and a Jira ticket.
- Store originals or exact original text locally and preserve source version, section, page/line or message/timestamp references.
- Maintain structured source metadata and a local semantic index; search with semantic retrieval plus lexical matching and metadata filters.
- Accept a question and explicit country, team/domain, optional client/project, and as-of date.
- Generate a small bounded set of alternative phrasings and route retrieval across relevant source categories.
- Produce an answer that is claim-level cited, scoped, and transparent about uncertainty.
- Show **Answer & evidence** and **For review** tabs; evidence popovers/drawers open the original stored source.
- Detect and visibly demonstrate a conflicting message, an outdated document, a duplicate, a country mismatch, and a missing answer component.
- Suggest at least one topic-relevant expert from seeded organisational relationships, with an explanation and evidence.
- Provide a polished SD Worx-inspired responsive interface and a deterministic demo path.

### P1 — implement after P0 is stable

- Add/administer knowledge entries directly in the UI; edit metadata, designate owner, approve/reject a proposed update, and mark supersession.
- Meeting-transcript import that extracts a draft summary, decisions, actions, participants, client/project, topics, and time-stamped evidence; human review before promotion to authoritative knowledge.
- Rich graph/expertise view and feedback controls (“useful,” “incorrect,” “send for review”).
- Optional consented CSV/JSON import of interactions from the last 30 days.
- A user-invoked Teams/Outlook export-assistant template that requests only permitted interaction metadata (name, organisational role if available, shared projects with evidence, and last interaction). Validate its output before import; do not claim that a prompt alone grants access to Microsoft data.

### P2 — integration-ready design, not a required live hackathon dependency

- Microsoft Entra ID directory and Microsoft Graph for users, roles, Teams, Outlook, and meeting metadata/content; Jira connector; scheduled sync; source ACL propagation.
- Automated meeting-agent ingestion only where recording/transcription and organisational consent permit it.
- Production-grade distributed indexing, object storage, SSO, multitenancy, retention, and scale testing.

## 5. Source model and ingestion requirements

### 5.1 Supported knowledge types

Model policies, manuals, procedures, checklists, analyses, chats, emails, meeting transcripts/decisions, Jira tickets, user-added notes, application records, and expert relationships. The P0 importer need only parse the listed demo formats, but the schema must distinguish all of these types.

### 5.2 Mandatory metadata

Every source version stores:

- Stable source ID and version ID; type; title; original filename/URI; content hash; ingestion time.
- Creator, owner (nullable), last editor (nullable), and approval status (`draft`, `approved`, `superseded`, `rejected`, `unknown`).
- Created, published, modified, effective-from, effective-until, and observed/meeting timestamps as **distinct nullable fields**. Never use upload time as the source's effective date.
- Country/jurisdiction, client, department/domain, project, product/system, audience, language, and tags where known; mark unknown scope explicitly.
- Supersedes/superseded-by references, parent thread or document family, and access-control label.
- Extracted text with section hierarchy and stable span positions. PDF evidence uses page and extracted line; chat/email evidence uses message ID and timestamp; meeting evidence uses transcript timestamp and meeting location when available.
- Original binary or full text stored locally for the P0 demo. Original links must resolve through the app, not a broken external URL.

### 5.3 Ingestion behavior

- Extract text and segment by meaningful sections/paragraphs before embedding. Preserve heading, page, line, and source-version linkage for every chunk.
- Store structured records and source metadata in a relational database. Treat embeddings as a **derived retrieval index**, not the authoritative content store. Rebuild the index from source records when needed.
- Detect exact duplicates using normalized content hash; flag likely semantic duplicates separately. Preserve all versions and their provenance.
- Do not silently turn a chat message, email, Jira comment, or meeting summary into an approved policy. These may become candidate evidence or review items.
- Make failures visible: unsupported format, extraction failure, missing metadata, or zero usable text. Do not claim such a source was indexed.

## 6. Query, routing, and retrieval

### 6.1 Input and context

The query form includes the question, country (required for jurisdiction-sensitive questions), domain/team (`HR`, `Pay`, `Time`, or other), optional client/project, and an as-of date. The UI may infer likely values from the question, but must show them for confirmation. If critical context is absent, ask one concise clarification or return a conditional answer clearly separated by scope. Never quietly assume Belgium or the latest date.

### 6.2 Bounded planning and routing

Use one lightweight planner/router to classify intent and likely knowledge domains, create **at most four** meaning-preserving query reformulations, and select retrieval paths. Paths can cover policy/manual/procedure/checklist, conversation/meeting, ticket/application, and expertise. Query expansions must not add unmentioned countries or clients. Log the reformulations and routes for debugging.

Implement retrieval workers as modules or bounded tasks. **Do not create one autonomous agent for every country × team × document type × integration combination.** Add a specialist only when it performs a distinct operation with measurable value. The recommended pipeline is:

`Question + context → plan/rewrite → parallel filtered retrieval → candidate grouping → applicability/version/conflict checks → consolidation/synthesis → claim validator → UI`

The final consolidation component receives **structured** candidate findings, not only free-form agent prose. It must preserve supporting and opposing evidence, distinguish established facts from inferences, and output claim/evidence mappings for validation before any friendly answer is displayed.

### 6.3 Retrieval rules

- Combine vector similarity with lexical search; apply access and scope filters **before** results reach the answer generator.
- Group hits by document family, topic, and answer component so one document with many chunks does not crowd out independent sources.
- Include both strong matching evidence and potentially contradictory evidence. Retrieval must not suppress a conflict merely because the preferred source ranks higher.
- Retain retrieval diagnostics: query, filters, candidate IDs, exclusions, scores, and selected spans.
- Cap work per query so the demo does not trigger unbounded agent calls. Provide a clear timeout/error state.

## 7. Trust, applicability, conflicts, and completeness

### 7.1 Decision order

For each candidate, check in this order:

1. **Permission:** may this user see the source?
2. **Applicability:** does country, client/project, domain, audience, and requested date match? Unknown scope is not equivalent to global scope.
3. **Authority and lifecycle:** approved source, explicit supersession, effective/expiry dates, owner, and source type.
4. **Evidence quality:** exact span supports the proposed claim; source is independently attributable and not an AI summary with no underlying reference.
5. **Consistency:** find material contradictions and duplicates across applicable sources.

Freshness alone cannot make a source authoritative. A newer Teams chat or email may identify a policy change, but it must surface as a **conflict for review** unless it is linked to an approved change/decision with appropriate scope and effective date. Never silently override an approved policy.

### 7.2 Trust facets, shown separately

| Aspiration | Signal shown to user | Question it answers |
| --- | --- | --- |
| Reliability | Owner, approval status, source type, exact citation | Who stands behind this claim? |
| Currentness | Modified date, effective interval, supersession | Is this version valid for the requested date? |
| Relevance | Country, client, domain, product, audience | Does it apply here? |
| Consistency | Conflicting claims and duplicate families | Do other sources disagree or repeat it? |
| Completeness | Required answer parts and evidence coverage | Which part is established or missing? |
| Expertise | Topic-specific contributions and consultations | Why is this person a useful contact? |

Use human-readable states such as **Supported**, **Needs review**, **Out of scope**, and **Unknown**. Do not show a single unexplained “trust percentage.” Seniority may be at most a small, disclosed tie-breaker for expert suggestions; topic-specific work matters more.

### 7.3 Claim-level answer policy

- Every factual answer sentence or bullet has one or more evidence IDs. Each ID maps to a real, visible source span.
- A claim cannot cite a source that does not directly support that claim. The validator must remove or mark unsupported claims before display.
- If an answer requires multiple components, show a small completeness breakdown: **supported**, **conflicted**, or **missing**, with evidence or reason for each component.
- When applicable sources disagree materially and no approved supersession resolves them, state the disagreement; do not choose a winner by semantic score or model preference.
- When evidence is missing, explicitly say what is unknown and offer a likely expert. Do not fill gaps from general model knowledge.
- Display why important retrieved sources were excluded, especially wrong country, expired version, unknown owner, or insufficient scope.

## 8. Knowledge graph and expert discovery

Represent a knowledge graph through relational entities and edges in P0; a separate graph database is optional. Minimum nodes: person, team, topic, country, client, project, document/source, meeting, and ticket. Minimum edges: owns, authored, edited, approved, participated in, answered, consulted on, relates to, applies to, supersedes, and conflicts with. Every edge records its underlying event/source and date. Do not infer a person is an expert solely from job title.

For an expert suggestion, score **per person and per topic** using permitted evidence such as recent relevant edits, answers, ticket participation, meeting decisions, and consultations. Show a plain-language explanation (“edited two Belgium payroll handover documents and answered a related ticket recently”) with source links. Disclose that the ranking is a suggestion, not proof of authority. Respect visibility rules and distinguish activity from approval authority.

A future Microsoft Teams/Outlook companion may ask a consenting user to import the last 30 days of interactions and extract name, organisational role, and shared projects **only where those fields are available and permitted**. The P0 demo uses synthetic records; it must not scrape personal inboxes or request broad permissions. Microsoft Entra ID can supply directory identity/role in a later phase. Meeting/chat/email data remains subject to access, retention, and source provenance rules.

## 9. Meeting-to-knowledge flow

Support a seeded or uploaded transcript that demonstrates:

`Meeting → transcript → extracted draft summary/decisions/actions/people/client/project/topics → reviewer approval → indexed knowledge`

Store meeting time, location or online meeting identifier if present, speakers, transcript timestamps, and source links. Each extracted item must point to the exact transcript span that supports it. Until a reviewer approves a decision, label it **draft/unverified** and show it in **For review** when it conflicts with an approved source. Reindex after approval or correction and retain the previous version/audit trail.

## 10. UI and interaction requirements

### 10.1 Visual direction

Use the current public SD Worx visual language as inspiration: generous whitespace, strong typography, dark ink text, blue as a primary action colour, restrained multicolour accent, clear hierarchy, and polished cards/spacing. The public site and June 2026 brand update are the design references in section 2. Create an original product interface; do not hotlink proprietary assets or copy the public site's CSS wholesale. Use an officially supplied logo if available, otherwise a simple text wordmark marked as a hackathon prototype. Define CSS variables for all colours and typography; verify desktop and mobile layouts visually.

### 10.2 Required screens

1. **Ask/answer workspace:** prominent query input, context chips/fields, example questions, loading/progress, answer status, and two tabs: **Answer & evidence** and **For review**.
2. **Evidence detail:** clicking `[E1]` opens a keyboard-accessible popover/drawer with exact highlighted excerpt, document title, section, page/line or timestamp, owner, relevant dates, scope, approval state, and **Open original**. Opening the original shows the stored file/text and the cited location where technically possible.
3. **For review:** grouped conflicts, duplicates, outdated versions, unknown owner/scope, and missing answer components. Each item gives the issue, implicated sources, and proposed next action. Missing knowledge can link to an expert suggestion.
4. **Expert card:** person, team/role if known, topic fit explanation, recent supporting activity, and source links. No ungrounded reputation score.
5. **Sources/admin:** list uploaded/seeded sources, metadata, status, version family, and ingestion errors. P1 adds add/edit/approve actions.

### 10.3 Usability

- The answer must remain readable without opening every citation; citations are adjacent to claims and evidence details are one click away.
- Label synthetic data and demo mode prominently but unobtrusively.
- Use accessible contrast, visible focus, semantic controls, keyboard operation for tabs/dialogs, and informative empty/error states.
- A source that cannot be opened must never display an “Open original” link that fails silently.

## 11. Suggested data model and API contract

### 11.1 Tables or equivalent entities

`users`, `teams`, `memberships`, `topics`, `sources`, `source_versions`, `source_spans`, `source_chunks`, `source_relations`, `knowledge_entities`, `knowledge_edges`, `expert_activity`, `queries`, `query_runs`, `answer_claims`, `evidence_links`, `review_items`, `audit_events`.

Key relationships: `answer_claims` reference exact `source_spans` through `evidence_links`; every span references a specific `source_version`; `source_relations` captures duplicate/supersedes/conflicts; `knowledge_edges` reference their supporting source/event. Never cite a source title alone when a span is available.

### 11.2 Minimum endpoints (or equivalent server actions)

- `POST /api/sources/import` — import file/structured record with metadata; return status and source ID.
- `GET /api/sources` and `GET /api/sources/{id}` — list metadata and retrieve permitted source/version.
- `GET /api/sources/{id}/content` — display/download stored original with access check.
- `POST /api/query` — accept question/context; return answer claims, evidence IDs, completeness, review items, exclusions, and expert suggestions.
- `GET /api/evidence/{id}` — return exact excerpt and source location.
- `GET /api/review-items` — list issues; P1 can add resolve/approve actions.
- `GET /api/health` — readiness including database, index, and optional LLM provider.

Return structured data from the backend. The front end must not infer trust status from prose. Version API contracts and validate inputs. Use stable IDs so a visible evidence link cannot resolve to a different source after reindexing.

## 12. Default implementation stack and architecture

If the repository is empty, default to React + TypeScript + Vite for the front end; Python FastAPI for ingestion, retrieval, rules, and answer orchestration; PostgreSQL with `pgvector` for relational data and embeddings; and Docker Compose for local startup. A lightweight full-text index in PostgreSQL can provide lexical search. Use CSS variables and a small component system for the interface. If Docker or pgvector is unavailable, a local SQLite + FAISS/Chroma-style adapter is acceptable **only if** the full demo and source provenance still work; document the substitution.

Keep model and embedding providers behind interfaces with environment-based configuration. Never commit API keys. Provide a deterministic fixture/demo mode that returns the seeded scenario even without a paid API key; label that mode. A live LLM mode may synthesize wording, but the deterministic applicability, version, conflict, and citation checks remain in code. Avoid an autonomous multi-agent framework unless it demonstrably improves the bounded pipeline in section 6.

For the no-key demo, use local embeddings or committed synthetic-fixture vectors plus lexical retrieval; if those cannot be packaged reliably, expose the demo's deterministic retrieval path clearly in the README. Never present a scripted demo answer as proof that arbitrary queries work.

## 13. Security and privacy requirements

- The P0 fixture contains no real payroll, employee, customer, or confidential correspondence.
- Enforce server-side access labels on source retrieval, evidence, originals, query context, and expert-activity views. Do not rely only on hidden UI controls. In demo mode, simple named roles and seeded permissions are sufficient.
- Treat retrieved documents, emails, chats, and transcripts as **data**, never as instructions to the model or app. Ignore prompt-injection attempts embedded in sources.
- Do not log full confidential source content or model prompts in production mode; provide safe debug logs for the demo.
- Validate uploads, restrict size/type, escape rendered source content, and protect against path traversal and script injection.
- Keep source edits, approvals, and answer generation auditable. Record who/what changed a source's status and when.
- Production connectors require least-privilege scopes, user/organisational consent, retention rules, and deletion handling before use. Do not request these permissions for the P0 demo.

## 14. Seeded demonstration and acceptance scenarios

Create a small, consistent synthetic corpus (roughly 12–20 records) around a **fictional Belgium payroll client handover**. Include an approved Belgium procedure with owner and effective date; an older superseded version; a near duplicate; a France-only policy; a later Teams message that contradicts the approved procedure but lacks approval; a meeting transcript proposing a change; a Jira ticket; and a domain expert whose activity is visible. Include a second answer component that no source covers. Avoid real legal/payroll advice: use a fictional workflow detail such as an internal handover checklist step.

### Required end-to-end tests

| ID | Scenario | Expected visible result |
| --- | --- | --- |
| AC-01 | Ask the seeded Belgium handover question with Belgium + Pay context | Answer includes only supported claims, each with a working `[E#]` citation. |
| AC-02 | Open a citation | Exact source text, version, owner, section and page/line or timestamp appear; original opens. |
| AC-03 | Search the same topic for France | Belgium-only content is not presented as applicable; France source is shown or uncertainty is stated. |
| AC-04 | Approved procedure conflicts with later unapproved Teams message | Approved procedure is not silently replaced; conflict appears in **For review** with both sources. |
| AC-05 | Older version and near duplicate are retrieved | Their relationship and status are visible; neither is silently discarded. |
| AC-06 | One required answer component has no evidence | Answer says exactly which part is unknown and does not invent a completion. |
| AC-07 | Ask who can help with the unknown component | Topic-relevant expert and the activity supporting the suggestion are shown. |
| AC-08 | Source is missing owner or effective date | Its missing trust signal is shown and it cannot receive a fully supported/approved badge. |
| AC-09 | User lacks source permission | Source content, evidence excerpt, original, and expert activity are inaccessible via API and UI. |
| AC-10 | Source contains text instructing the assistant to ignore rules | The content is treated as source text; it does not alter answer policy or expose data. |
| AC-11 | No LLM key is set | App starts and deterministic demo scenario still works; live mode clearly reports its unavailable provider. |
| AC-12 | Reload after import (and after approval if P1 is built) | Stored source/version, index, review state, and citations persist and still resolve. |

Add focused automated tests for applicability, supersession, conflict handling, citation validation, and access checks. Test the user journey in a browser at desktop and mobile widths. The demo should run from documented setup steps, without hand-editing the database.

## 15. Hackathon delivery criteria

The result is complete when the team can start the app from a clean checkout, load the synthetic corpus, run the question → answer → evidence → review → expert journey, and explain every trust decision in a short demo. Include a clear README and sample environment file. Keep the repository public and accessible for judging only when the team is ready; do not expose secrets or private data. The participant guide asks for a short description, a demo video under three minutes, a GitHub repository link, and Aikido audit screenshots before and after fixes. Run the available Aikido audit before submission if access is provided, fix material findings, and record what was checked.

## 16. Explicit non-goals and unresolved decisions

The hackathon proof of concept does **not** need to index all 10,000 employees, all customers, all countries, or every SD Worx system. It does not need live Microsoft or Jira integration, a meeting bot that joins real calls, or automated promotion of conversation snippets into policy. Those require real data, access, governance, and separate validation.

Decisions the team may supply before implementation: existing repository/stack, official logo or brand assets, available LLM/embedding provider, whether a live connector is authorised, and the exact synthetic demo story. If none is supplied, proceed with the defaults above and record assumptions in the README.
