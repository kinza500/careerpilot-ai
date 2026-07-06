"""Embeddings for semantic matching.

Default path uses OpenAI's embeddings API, truncated to 384 dimensions to
match the vector(384) columns — this doesn't cross a new confidentiality
boundary since resume/job text already goes to OpenAI's API for the LLM
agents (resume understanding, matching reasoning, writer/critic) under the
same no-training guarantee documented in docs/SECURITY.md.

For a fully local / air-gapped deployment (LLM_PROVIDER=ollama), embeddings
fall back to a local sentence-transformers model instead, so no text leaves
the host at all in that mode.
"""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings

settings = get_settings()

DIMENSIONS = 384


def _use_local() -> bool:
    return settings.llm_provider == "ollama"


@lru_cache
def _local_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings.embedding_model)


def _openai_embed(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    # OpenAI's API rejects empty strings outright (sentence-transformers
    # embeds them fine as a near-zero vector) — substitute a single space so
    # an empty description/summary doesn't blow up the whole batch.
    res = client.embeddings.create(
        model=settings.openai_embedding_model,
        input=[t or " " for t in texts],
        dimensions=DIMENSIONS,
    )
    return [d.embedding for d in res.data]


def embed(text: str) -> list[float]:
    return embed_many([text])[0]


def embed_many(texts: list[str]) -> list[list[float]]:
    texts = [t or "" for t in texts]
    if _use_local():
        vecs = _local_model().encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]
    return _openai_embed(texts)
