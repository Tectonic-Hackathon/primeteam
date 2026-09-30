#!/usr/bin/env bash
# One-shot: start containers, pull the embedding model, seed, serve on http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")"
colima status >/dev/null 2>&1 || colima start --cpu 4 --memory 6
docker-compose up -d
until docker exec grounded-db pg_isready -U grounded >/dev/null 2>&1; do sleep 1; done
docker exec grounded-ollama ollama pull nomic-embed-text >/dev/null 2>&1 || echo "ollama pull failed, using offline embeddings"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r backend/requirements.txt
[ -f .env ] || cp .env.example .env
(cd backend && ../.venv/bin/python seed/seed.py)
cd backend && exec ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 "$@"
