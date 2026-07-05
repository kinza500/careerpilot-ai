"""Extension-point stubs for the agents beyond the deployable core.

Each has a real, typed interface and a working-but-minimal implementation so the
pipeline runs end-to-end today. TODOs mark where to deepen each one. This is the
intended place to grow toward the full 11-agent proposal.
"""
from __future__ import annotations

from app.agents.llm import get_llm
from app.config import get_settings

settings = get_settings()


# --- Agent 4: Skill-Gap Analysis -------------------------------------------
def analyse_skill_gap(profile: dict, job: dict) -> dict:
    """Return {readiness: 0-100, missing_skills: [...], learning_plan: [...]}.
    TODO: enrich with a curated learning-resource catalogue + Tavily search."""
    have = {s.lower() for s in profile.get("skills", [])}
    desc = (job.get("description") or "").lower()
    # naive keyword gap; replace with LLM extraction of required skills
    common = ["docker", "aws", "kubernetes", "sql", "react", "python", "typescript"]
    missing = [s for s in common if s in desc and s not in have]
    readiness = max(0, 100 - 15 * len(missing))
    return {
        "readiness": readiness,
        "missing_skills": missing,
        "learning_plan": [f"Short crash course on {s}" for s in missing],
    }


# --- Agent 6: Company Research (Tavily search -> LLM brief) ----------------
def research_company(company: str | None) -> dict:
    """Return a short, grounded company insight brief for an applicant, as a
    scannable bullet list rather than prose, plus whether it's actually
    grounded in a live web search (vs. an ungrounded LLM guess) — this is
    surfaced to the user directly so they can see real research happened,
    not just trust a generic claim.

    Uses Tavily's search API (built for agents) to pull fresh, real web context,
    then has the LLM synthesise a brief grounded in those snippets. If no Tavily
    key is configured (or the call fails), it degrades to an ungrounded LLM
    brief and is labelled as such. Firecrawl is not needed here — this is a
    search task, not a deep single-URL scrape. If you later want full-page
    depth (e.g. the careers page), add tavily .extract() or .crawl() on a
    specific URL.
    """
    if not company:
        return {"brief": "", "grounded": False, "sources": []}

    context = ""
    grounded = False
    sources: list[dict] = []
    if settings.tavily_api_key:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=settings.tavily_api_key)
            # Two focused searches instead of one broader one — a single query
            # covering culture+tech+financials would dilute the 5 results
            # across too many topics. This works the same for a Pakistani
            # startup or a US public company: Tavily is plain web search, not
            # a stock-market API, so it isn't limited to any one exchange or
            # country — it just surfaces whatever's genuinely written online.
            queries = [
                f"{company} company culture, tech stack, hiring",
                f"{company} revenue, funding, financial health, stock performance, layoffs, market conditions",
            ]
            # Cap each topic's snippets independently (not the combined
            # string) — otherwise a wordy first topic silently crowds the
            # second one out entirely before the LLM ever sees it.
            blocks = []
            seen_urls: set[str] = set()
            for q in queries:
                res = client.search(query=q, max_results=4, search_depth="advanced")
                results = res.get("results", [])
                topic_snippets = "\n\n".join(
                    f"- {r.get('title','')}: {r.get('content','')}" for r in results
                )
                if topic_snippets:
                    blocks.append(topic_snippets[:3000])
                # Real URLs straight from Tavily's own results — never passed
                # through the LLM, so there's no chance of a hallucinated link.
                for r in results:
                    url = r.get("url")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        sources.append({"title": r.get("title") or url, "url": url})
            context = "\n\n".join(blocks)
            grounded = bool(context)
        except Exception as exc:  # network / key / SDK — degrade gracefully
            print(f"[company_research] Tavily unavailable: {exc}")

    try:
        system = (
            "You brief a job applicant on a company. Use the provided web context "
            "when present and cite nothing you cannot see. Do not invent facts or "
            "hedge with vague filler. Respond ONLY as 3-6 short bullet points, one "
            "per line, each starting with '- ' and a bolded label, covering "
            "whichever of these you have real information for: Culture, Tech "
            "stack, Recent news, Financial health (revenue, funding, stock "
            "performance, layoffs, market conditions — for private/unlisted "
            "companies use whatever funding or business-performance news "
            "exists instead), Why it's relevant to this applicant. Skip any "
            "label you have no grounded information for rather than guessing."
        )
        user = f"Company: {company}\n\nWeb context (may be empty):\n{context or '(none)'}"
        brief = get_llm().complete(system, user, max_tokens=420)
        return {"brief": brief, "grounded": grounded, "sources": sources[:8]}
    except Exception:
        return {"brief": "", "grounded": False, "sources": []}


# --- Interview scheduling extraction (reply text -> suggested calendar event) --
def extract_interview_schedule(reply_text: str, job: dict) -> dict | None:
    """Look at a genuine reply's text and, ONLY if it states a specific
    interview date and time, return a structured suggestion for a calendar
    event. Never guesses a date from vague language ("we'll be in touch",
    "sometime next week") — returns None rather than invent a slot. The
    caller always surfaces this to the user to confirm before anything is
    ever written to their calendar; nothing here creates an event itself.
    """
    if not reply_text or not reply_text.strip():
        return None
    from datetime import date as _date
    today = _date.today().isoformat()
    system = (
        f"Today's date is {today}. You read one email reply to a job "
        "application and decide whether it states a SPECIFIC interview date "
        "and time (not a vague window like 'next week' or 'we'll follow up'). "
        "Resolve relative dates ('this Thursday', 'the 14th') against today's "
        "date. Respond as JSON ONLY with these keys: "
        '"found" (boolean), "date" (YYYY-MM-DD or null), "time" (24h HH:MM in '
        'the timezone the email implies, or null), "timezone" (an IANA name '
        'like "Asia/Karachi" if inferable from the email/job location, else '
        '"UTC"), "duration_minutes" (int, default 60 if unstated), '
        '"location_or_method" (e.g. "Video call — link in email", "Phone '
        'call", or an address, or null), "summary" (short string like '
        '"Interview: Backend Engineer at Acme"). If no specific date+time is '
        'stated, set "found" to false and leave the rest null.'
    )
    user = f"Role: {job.get('title')} at {job.get('company')}\n\nEmail reply:\n{reply_text[:4000]}"
    try:
        result = get_llm().complete_json(system, user, max_tokens=300)
        return result if result.get("found") and result.get("date") and result.get("time") else None
    except Exception as exc:
        print(f"[interview_schedule] extraction failed: {exc}")
        return None


# --- Agent 9: Application Tracker ------------------------------------------
def tracker_summary(applications: list[dict]) -> dict:
    """TODO: Notion MCP sync + reminder scheduling via Celery beat."""
    by_status: dict[str, int] = {}
    for a in applications:
        by_status[a["status"]] = by_status.get(a["status"], 0) + 1
    return {"counts": by_status, "total": len(applications)}


# --- Agent 10: Follow-up Email --------------------------------------------
def draft_followup(job: dict, days_since: int) -> str:
    """TODO: time-aware templates + Gmail MCP send (human-approved)."""
    return get_llm().complete(
        "You draft a brief, polite follow-up email after no response to a job "
        "application. Never sound pushy.",
        f"Role: {job.get('title')} at {job.get('company')}. Days since applying: {days_since}.",
        max_tokens=400,
    )


# --- Agent 11: Interview Prep — see app/agents/interview_agent.py ----------
# (the real adaptive, multi-turn implementation lives there; this stub's
# static one-shot question list has been superseded)
