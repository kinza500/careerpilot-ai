"""Agent 11 — Interview Prep: a live, adaptive mock interview.

No fixed question bank and no branching logic — every turn re-sends the full
running transcript to the LLM, which reacts to whatever the candidate actually
said (probing a vague answer, following up on something interesting, or
moving on). The realism comes from grounding the interviewer persona in real
data already gathered for this application: the job description, the
candidate's own resume skills, the skill gap against this specific job, and
the company research brief (never inventing facts beyond what's there).
"""
from __future__ import annotations

from app.agents.llm import get_llm
from app.agents.stubs import analyse_skill_gap
from app.config import get_settings

settings = get_settings()

# A real interview round has a rough shape and a natural end, not an
# indefinite Q&A — 5 keeps a practice session short enough to actually finish.
MAX_QUESTIONS = 5


def _interview_model() -> str | None:
    # Only OpenAI has a distinct, cheaper model configured for this agent —
    # conversational Q&A doesn't need the top-tier model used for cover
    # letters. Other providers fall back to whatever they're already set to.
    return settings.openai_interview_model if settings.llm_provider == "openai" else None


def _persona(profile: dict, job: dict, company_research: str, question_number: int) -> str:
    missing = analyse_skill_gap(profile, job).get("missing_skills", [])
    skills = ", ".join(profile.get("skills", [])[:20]) or "unspecified"
    return (
        "You are an experienced interviewer at "
        f"{job.get('company') or 'the hiring company'}, conducting a realistic "
        f"mock interview for the role of {job.get('title')}. Stay in character "
        "as a real human interviewer at all times — never mention you are an "
        "AI or language model, never break character.\n\n"
        f"Job description:\n{(job.get('description') or '')[:3000]}\n\n"
        f"Candidate's resume skills: {skills}\n\n"
        "Skills the job wants that aren't on the candidate's resume: "
        f"{', '.join(missing) or 'none obviously missing'}\n\n"
        "What's known about the company (use only these facts, never invent "
        f"more):\n{company_research or '(no company research available)'}\n\n"
        f"This interview lasts exactly {MAX_QUESTIONS} questions total. You are "
        f"about to ask question {question_number} of {MAX_QUESTIONS}. Pace "
        "yourself across the whole interview — don't cram multiple topics "
        f"into one question early on. If this is question {MAX_QUESTIONS} (the "
        "last one), still ask a real, substantive question — don't turn it "
        "into a farewell.\n\n"
        "Interview style: a natural mix of behavioural (STAR-style), "
        "technical/role-specific, and one situational curveball question "
        "across the whole session — not a checklist, and not in a fixed "
        "order. Ask ONE question at a time. React to the candidate's last "
        "answer: if it's vague or shallow, probe deeper on that same point "
        "instead of moving to a new topic; if a missing skill is relevant, "
        "ask how they'd approach that gap; if they mention something "
        "interesting, follow up on it. Keep each message brief (2-4 "
        "sentences), like real spoken dialogue, not an essay or a list."
    )


def start_interview(profile: dict, job: dict, company_research: str = "") -> str:
    system = _persona(profile, job, company_research, question_number=1)
    return get_llm().chat(
        system,
        [{"role": "user", "content": "Begin the interview. Greet the candidate briefly, then ask your first question."}],
        max_tokens=300, model=_interview_model(),
    )


def next_turn(profile: dict, job: dict, company_research: str, transcript: list[dict]) -> str:
    """transcript: [{"role": "interviewer" | "candidate", "content": str}, ...],
    already including the candidate's latest answer as the last entry."""
    asked_so_far = sum(1 for t in transcript if t["role"] == "interviewer")
    system = _persona(profile, job, company_research, question_number=asked_so_far + 1)
    messages = [
        {"role": "assistant" if t["role"] == "interviewer" else "user", "content": t["content"]}
        for t in transcript
    ]
    return get_llm().chat(system, messages, max_tokens=300, model=_interview_model())


def end_interview(job: dict, transcript: list[dict]) -> dict:
    """Debrief on the whole session — same grounded self-critique shape used
    elsewhere (a score plus concrete, quoted notes, not vague encouragement)."""
    convo = "\n".join(
        f"{'Interviewer' if t['role'] == 'interviewer' else 'Candidate'}: {t['content']}"
        for t in transcript
    )[:8000]
    system = (
        "You are an interview coach reviewing a completed mock interview "
        "transcript. Be specific and grounded only in what was actually said "
        "in the transcript below — do not invent details or generic advice "
        "unrelated to it. Respond as JSON with exactly these keys: "
        '"readiness_score" (0-100 integer), "strengths" (array of short '
        'strings), "areas_to_improve" (array of short strings), '
        '"weakest_answer" (a short quote or summary of the weakest moment), '
        '"suggested_better_answer" (a stronger version of that one answer).'
    )
    user = f"Role: {job.get('title')} at {job.get('company')}\n\nTranscript:\n{convo}"
    return get_llm().complete_json(system, user, max_tokens=700, model=_interview_model())
