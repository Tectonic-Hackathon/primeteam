"""Embeddings via a local Ollama container, with a deterministic offline fallback.

The fallback is a hashed word/bigram embedding so the whole demo still runs
without any model download. Retrieval is hybrid (vector + full-text), so the
lexical side carries the fallback."""
import hashlib
import math
import re
import httpx
from .config import OLLAMA_URL, EMBED_MODEL, EMBED_DIM

_TOKEN = re.compile(r"[a-z0-9€£%]+")
_mode = {"backend": None}


def _hashed(text: str) -> list[float]:
    vec = [0.0] * EMBED_DIM
    toks = _TOKEN.findall(text.lower())
    grams = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
    for g in grams:
        h = int(hashlib.md5(g.encode()).hexdigest(), 16)
        idx = h % EMBED_DIM
        sign = 1.0 if (h >> 20) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _ollama_available() -> bool:
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2.0)
        r.raise_for_status()
        names = [m["name"].split(":")[0] for m in r.json().get("models", [])]
        return EMBED_MODEL.split(":")[0] in names
    except Exception:
        return False


def backend() -> str:
    if _mode["backend"] is None:
        _mode["backend"] = "ollama" if _ollama_available() else "hashed"
    return _mode["backend"]


def embed(text: str) -> list[float]:
    if backend() == "ollama":
        try:
            r = httpx.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": text},
                timeout=60.0,
            )
            r.raise_for_status()
            emb = r.json()["embedding"]
            if len(emb) == EMBED_DIM:
                return emb
        except Exception:
            _mode["backend"] = "hashed"
    return _hashed(text)


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
