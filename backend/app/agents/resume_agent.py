"""Agent 1 — Resume Understanding.

Input: decrypted resume bytes (in memory only). Output: structured skill profile
+ an embedding of the profile summary for semantic matching. The raw bytes are
handled in-memory and never logged.
"""
from __future__ import annotations

import io

from app.agents.embeddings import embed
from app.agents.llm import get_llm
from app.agents.prompts import RESUME_UNDERSTANDING


def _extract_text(data: bytes, mime_type: str, filename: str) -> str:
    name = (filename or "").lower()
    if mime_type == "application/pdf" or name.endswith(".pdf"):
        import fitz  # PyMuPDF
        doc = fitz.open(stream=data, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    if name.endswith(".docx") or "word" in mime_type:
        import docx
        d = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in d.paragraphs)
    # plain text fallback
    return data.decode("utf-8", errors="ignore")


def parse_resume(data: bytes, mime_type: str, filename: str) -> tuple[dict, list[float]]:
    text = _extract_text(data, mime_type, filename)
    text = text[:20000]  # bound token cost
    profile = get_llm().complete_json(RESUME_UNDERSTANDING, text)
    summary = profile.get("summary") or " ".join(profile.get("skills", []))
    return profile, embed(summary)
