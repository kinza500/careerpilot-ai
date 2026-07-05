"""Local embeddings.

Using sentence-transformers on the host (rather than a hosted embedding API)
means resume and job text used for semantic matching never leaves our
infrastructure — the confidentiality-first choice, and free. Dim = 384
(all-MiniLM-L6-v2), matching the vector(384) columns.
"""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings

settings = get_settings()


@lru_cache
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings.embedding_model)


def embed(text: str) -> list[float]:
    vec = _model().encode(text or "", normalize_embeddings=True)
    return vec.tolist()


def embed_many(texts: list[str]) -> list[list[float]]:
    vecs = _model().encode([t or "" for t in texts], normalize_embeddings=True)
    return [v.tolist() for v in vecs]
