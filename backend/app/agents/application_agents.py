"""Agents 5/7/8 — Resume Optimisation, Writer, and Critic.

These run as a self-correcting loop: Writer drafts, Critic reviews, and if the
Critic rejects, the Writer revises (bounded retries). Nothing here sends
anything — output is a draft package that a human must approve.
"""
from __future__ import annotations

import json

from app.agents.llm import get_llm
from app.agents.prompts import CRITIC, RESUME_OPTIMISATION, WRITER


def optimise_resume(profile: dict, job: dict) -> str:
    llm = get_llm()
    return llm.complete(
        RESUME_OPTIMISATION,
        json.dumps({"profile": profile, "job": job})[:12000],
        max_tokens=2500,
    )


def write_documents(profile: dict, job: dict, company_context: str = "") -> dict:
    llm = get_llm()
    payload = json.dumps({"profile": profile, "job": job, "company_context": company_context})[:12000]
    return llm.complete_json(WRITER, payload, max_tokens=2000)


def critique(job: dict, tailored_resume: str, docs: dict) -> dict:
    llm = get_llm()
    payload = json.dumps({
        "job": job,
        "tailored_resume": tailored_resume[:6000],
        "cover_letter": docs.get("cover_letter", "")[:4000],
        "outreach_email": docs.get("outreach_email", "")[:2000],
    })
    return llm.complete_json(CRITIC, payload, max_tokens=1000)


def prepare_application(profile: dict, job: dict, company_context: str = "",
                        max_revisions: int = 2) -> dict:
    """Full Stage-6/7 loop. Returns the draft package + critic notes.
    Status stays 'review' — approval is a separate human action."""
    tailored = optimise_resume(profile, job)
    docs = write_documents(profile, job, company_context)

    notes = {}
    for _ in range(max_revisions + 1):
        notes = critique(job, tailored, docs)
        if notes.get("approved"):
            break
        # Revise with critic instructions folded into the writer context.
        docs = write_documents(
            profile, job,
            company_context + "\nRevision instructions: " + notes.get("revision_instructions", ""),
        )

    return {
        "tailored_resume": tailored,
        "cover_letter": docs.get("cover_letter", ""),
        "outreach_email": docs.get("outreach_email", ""),
        "critic_notes": notes,
    }
