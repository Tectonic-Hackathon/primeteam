import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://grounded:grounded@localhost:5433/grounded")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11435")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = 768
LLM_BACKEND = os.getenv("LLM_BACKEND", "template")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:3b")
TODAY = os.getenv("GROUNDED_TODAY", "2026-09-30")
