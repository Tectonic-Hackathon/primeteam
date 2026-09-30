> Team working doc: https://docs.google.com/document/d/1Sd3y1srWgh8ZwH282dtvsXq3oxlC1VOh6FKil8sWyVY/edit?usp=sharing

# Grounded · SD Worx knowledge assistant

Ask once. Get the answer, the evidence and who to trust. Every sentence is cited to document → section → line, every source has
an explainable confidence, and everything that conflicts, duplicates, is outdated, unofficial or missing shows up as a fixable issue.

**Submission write-up (problem, approach, technical details): [SUBMISSION.md](SUBMISSION.md)**

## Run

```bash
./run.sh            # starts colima if needed, Postgres+pgvector and Ollama containers, pulls the embedding model, seeds, serves
open http://localhost:8000
```

No paid API. Third parties run only as containers: `pgvector/pgvector:pg16` (port 5433) and `ollama/ollama` with the small
`nomic-embed-text` model (port 11435). Reseed after editing the corpus: `cd backend && ../.venv/bin/python seed/seed.py`.

## Demo

Click the example chips on the landing page. They run the team's two fictional datasets (payroll cutoff, Northstar parental leave)
plus our own set. Highlights: the 80% vs 100% parental-leave answer with four kinds of issue, the public-allowance question the
system refuses and routes to the right expert, the Belgian cutoff deadline with a conflicting FAQ and an unofficial quick guide, and
the French deadline that lives only in a chat and can be captured as a note in one click.

- **Answer** tab: verdict, confidence, bold answer sentence, citations, sources with an eye icon for the trust breakdown.
- **Issues** tab: conflicts, duplicates, outdated, wrong country, unofficial, undocumented, review overdue, each with fix actions and undo.
- Side card: who knows this, or who to ask when there is no reliable answer, with an eye icon for their track record.
- **Add knowledge**: write a note, or sync connected sources (SharePoint, Confluence, Jira, Teams, Outlook, Meetings; demo fixtures without credentials).

Known gaps: "Is a correction run free?" leads with the wrong sentence of the right procedure; "Can I trust the quick guide?" has no
country in the question. Both are left out of the chips.

## Layout

| Path | Purpose |
|---|---|
| `backend/app/pipeline/` | context → planner → retrieval → trust → conflicts → experts → consolidate |
| `backend/app/connectors/` | source connectors, fixtures, ingest with hashing, versions and supersession |
| `backend/app/freshness.py` | review periods, staleness sweep, owner confirmation |
| `backend/seed/corpus.py` | fictional corpus (three datasets) |
| `backend/app/static/` | UI, no build step |
