"""Agent 3 — Matching & Ranking.

Two-stage: (1) cheap vector cosine similarity between the profile embedding and
each job embedding produces a base score and shortlists; (2) the LLM produces a
human-readable explanation and per-factor breakdown for the shortlist only,
which keeps token cost bounded while every surfaced result stays explainable.
"""
from __future__ import annotations

import json

from app.agents.llm import get_llm
from app.agents.prompts import MATCHING_REASONING


def cosine(a: list[float], b: list[float]) -> float:
    # embeddings are already L2-normalised, so dot product == cosine similarity
    return float(sum(x * y for x, y in zip(a, b)))


def rank(profile: dict, profile_emb: list[float], jobs: list[dict],
         explain_top: int = 10) -> list[dict]:
    """jobs: list of {id, title, company, description, embedding}. Returns list
    of {job_id, score, reasoning, factors} sorted desc."""
    scored = []
    for j in jobs:
        base = cosine(profile_emb, j["embedding"]) if j.get("embedding") else 0.0
        scored.append({"job": j, "base": base})
    scored.sort(key=lambda s: s["base"], reverse=True)

    llm = get_llm()
    results = []
    for i, s in enumerate(scored):
        job = s["job"]
        if i < explain_top:
            try:
                out = llm.complete_json(
                    MATCHING_REASONING,
                    json.dumps({
                        "candidate": profile,
                        "job": {k: job.get(k) for k in ("title", "company", "location", "description")},
                    })[:12000],
                )
                factors = out.get("factors", {})
                reasoning = out.get("reasoning", "")
            except Exception as exc:
                factors, reasoning = {}, f"(reasoning unavailable: {exc})"
        else:
            factors, reasoning = {}, "Below shortlist threshold; ranked by semantic similarity."
        # blend semantic base with factor average when available
        fscore = sum(factors.values()) / len(factors) if factors else s["base"]
        final = round(100 * (0.5 * s["base"] + 0.5 * fscore), 1)
        results.append({
            "tmp_id": job["tmp_id"],
            "score": final,
            "reasoning": reasoning,
            "factors": factors or None,
        })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results
