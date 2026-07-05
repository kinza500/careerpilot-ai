"""Agent 2 — Job Discovery & Aggregation.

Wraps JobSpy to pull listings across boards, normalises fields, and embeds each
description for semantic matching. If JobSpy is unavailable or a board blocks
the request, we degrade gracefully with an empty result rather than crashing
the pipeline. Respect each site's ToS and rate limits in production.
"""
from __future__ import annotations

from datetime import date, timedelta

import httpx

from app.agents.embeddings import embed_many
from app.config import get_settings

settings = get_settings()

MAX_LISTING_AGE_DAYS = 30


def _normalise(row: dict) -> dict:
    from uuid import uuid4

    def g(*keys):
        for k in keys:
            v = row.get(k)
            if v not in (None, ""):
                return v
        return None

    return {
        # stable per-run id so ranking results can be mapped back after sorting
        "tmp_id": str(uuid4()),
        "source": g("site", "source"),
        "external_id": str(g("id", "job_url", "job_url_direct") or ""),
        "title": g("title") or "Untitled role",
        "company": g("company"),
        "location": g("location", "city"),
        "remote": bool(g("is_remote")) if g("is_remote") is not None else None,
        "salary": g("salary", "min_amount"),
        "url": g("job_url", "job_url_direct"),
        "company_url": g("company_url", "company_url_direct"),
        "description": (g("description") or "")[:8000],
        # Only ever a real address JobSpy found written in the posting itself
        # (never invented) — most listings won't have one since job boards
        # route applications through their own portals, not email.
        "contact_email": (g("emails") or "").split(",")[0].strip() or None,
        "date_posted": g("date_posted"),
    }


def _normalise_jooble(row: dict) -> dict:
    from uuid import uuid4

    return {
        "tmp_id": str(uuid4()),
        "source": "jooble",
        "external_id": str(row.get("id") or ""),
        "title": row.get("title") or "Untitled role",
        "company": row.get("company") or None,
        "location": row.get("location") or None,
        # Jooble has no structured remote flag — left unknown rather than guessed.
        "remote": None,
        "salary": row.get("salary") or None,
        "url": row.get("link"),
        # Jooble is a pure aggregator: no separate company site, no contact
        # address ever appears in its payload — never fabricated here either.
        "company_url": None,
        "description": (row.get("snippet") or "")[:8000],
        "contact_email": None,
        "date_posted": row.get("updated"),
    }


def _fetch_jooble(query: str, country: str, limit: int, work_type: str) -> list[dict]:
    """Aggregator API (https://jooble.org/api/about) used as a supplemental
    source — it covers ~70 countries including Pakistan and the Gulf, where
    JobSpy's own scrapers are blocked (Bayt) or unsupported (Glassdoor).
    Requires JOOBLE_API_KEY; silently skipped if not configured."""
    if not settings.jooble_api_key:
        return []
    # Jooble has no structured remote/hybrid filter, unlike JobSpy's is_remote
    # toggle above — surfaced as a search-term hint instead, same workaround.
    keywords = f"{query} {work_type}" if work_type in ("remote", "hybrid") else query
    try:
        resp = httpx.post(
            f"https://jooble.org/api/{settings.jooble_api_key}",
            json={"keywords": keywords, "location": country, "ResultOnPage": str(limit)},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("jobs", [])
    except Exception as exc:  # this source's outage shouldn't sink the rest
        print(f"[discovery] jooble unavailable: {exc}")
        return []


def _normalise_serpapi(row: dict) -> dict:
    from uuid import uuid4

    apply_options = row.get("apply_options") or []
    url = apply_options[0].get("link") if apply_options else row.get("share_link")
    return {
        "tmp_id": str(uuid4()),
        "source": "google_jobs",
        "external_id": str(row.get("job_id") or ""),
        "title": row.get("title") or "Untitled role",
        "company": row.get("company_name") or None,
        "location": row.get("location") or None,
        "remote": bool((row.get("detected_extensions") or {}).get("work_from_home")) or None,
        "salary": (row.get("detected_extensions") or {}).get("salary"),
        "url": url,
        # Google Jobs aggregates postings from many boards' own pages — no
        # separate company-site field, no contact address in this schema.
        "company_url": None,
        "description": (row.get("description") or "")[:8000],
        "contact_email": None,
        # Only a relative string ("3 days ago") is available, not a real date
        # — left unparsed so _is_within_max_age() falls back to keeping it
        # (same lenient handling as any other job with no verifiable date).
        "date_posted": None,
    }


def _fetch_serpapi(query: str, country: str, limit: int, work_type: str) -> list[dict]:
    """SerpApi's Google Jobs engine (https://serpapi.com/google-jobs-api) —
    licensed access to Google's own job index, which itself aggregates
    postings from many boards Google has indexed. A supplemental source, not
    a bypass of any blocked site. Requires SERPAPI_KEY; silently skipped if
    not configured."""
    if not settings.serpapi_key:
        return []
    keywords = f"{query} {work_type}" if work_type in ("remote", "hybrid") else query
    try:
        resp = httpx.get(
            "https://serpapi.com/search",
            params={
                "engine": "google_jobs", "q": keywords, "location": country,
                "api_key": settings.serpapi_key,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("jobs_results", [])[:limit]
    except Exception as exc:  # this source's outage shouldn't sink the rest
        print(f"[discovery] serpapi unavailable: {exc}")
        return []


def _is_within_max_age(job: dict) -> bool:
    # hours_old is passed to scrape_jobs as a hint, but not every scraper
    # honours it (Bayt ignores it entirely; Google only maps it to an
    # approximate "last month" bucket) — this is the actual enforcement.
    # Jobs with no posted-date data can't be verified either way, so they're
    # kept rather than silently dropped.
    raw = job.get("date_posted")
    if not raw:
        return True
    try:
        posted = raw if isinstance(raw, date) else date.fromisoformat(str(raw)[:10])
    except ValueError:
        return True
    return posted >= date.today() - timedelta(days=MAX_LISTING_AGE_DAYS)


# Cities that share a name across two countries where a scraped source
# (confirmed: Indeed's Pakistan-domain search) has been caught mislabeling the
# other country's listings with the wrong country tag — e.g. Tata Consultancy
# Services' real Hyderabad, INDIA campus showing up tagged "Hyderabad, PSD, PK"
# in Pakistan searches. TCS has no Pakistan operations, so this is a confirmed
# data-quality bug at the source, not a legitimate local listing.
AMBIGUOUS_CITY_EXCLUSIONS = {
    "pakistan": {"hyderabad"},
}


def _city_of(location: str | None) -> str:
    return (location or "").split(",")[0].strip().lower()


DEFAULT_SITES = ["indeed", "linkedin", "google"]

# Extra boards worth querying per destination country, on top of the global
# defaults above. Glassdoor is only listed where JobSpy actually has coverage
# (it has no Pakistan/Gulf support and raises instead of returning an empty
# frame — which would otherwise take down every other site in the same call,
# so it's deliberately left out for those). Bayt is MENA-focused; ZipRecruiter
# is US/Canada-only.
COUNTRY_SITES = {
    "pakistan": DEFAULT_SITES + ["bayt"],
    "united arab emirates": DEFAULT_SITES + ["bayt"],
    "saudi arabia": DEFAULT_SITES + ["bayt"],
    "qatar": DEFAULT_SITES + ["bayt"],
    "kuwait": DEFAULT_SITES + ["bayt"],
    "usa": DEFAULT_SITES + ["glassdoor", "zip_recruiter"],
    "canada": DEFAULT_SITES + ["glassdoor", "zip_recruiter"],
    "uk": DEFAULT_SITES + ["glassdoor"],
    "germany": DEFAULT_SITES + ["glassdoor"],
    "australia": DEFAULT_SITES + ["glassdoor"],
    "singapore": DEFAULT_SITES + ["glassdoor"],
    "ireland": DEFAULT_SITES + ["glassdoor"],
    "netherlands": DEFAULT_SITES + ["glassdoor"],
    "new zealand": DEFAULT_SITES + ["glassdoor"],
}


def discover_jobs(
    query: str, location: str | None, limit: int, work_type: str = "remote",
) -> list[dict]:
    per_source: dict[str, list[dict]] = {}
    country = (location or "Pakistan").strip()
    sites = COUNTRY_SITES.get(country.lower(), DEFAULT_SITES)
    try:
        from jobspy import scrape_jobs
        # JobSpy only exposes a remote/not-remote toggle; "hybrid" has no direct
        # filter, so we surface it as a search hint instead.
        search_term = f"{query} hybrid" if work_type == "hybrid" else query
        for site in sites:
            try:
                df = scrape_jobs(
                    site_name=[site],
                    search_term=search_term,
                    location=country,
                    is_remote=work_type == "remote",
                    country_indeed=country,
                    results_wanted=limit,
                    hours_old=720,
                )
                rows = df.fillna("").to_dict("records") if df is not None and not df.empty else []
                per_source[site] = [_normalise(r) for r in rows]
            except Exception as exc:  # this site's outage shouldn't sink the rest
                print(f"[discovery] {site} unavailable: {exc}")
                per_source[site] = []
    except Exception as exc:  # JobSpy itself missing/broken — degrade, don't crash
        print(f"[discovery] JobSpy unavailable: {exc}")
        per_source = {}

    per_source["jooble"] = [
        _normalise_jooble(r) for r in _fetch_jooble(query, country, limit, work_type)
    ]
    per_source["google_jobs"] = [
        _normalise_serpapi(r) for r in _fetch_serpapi(query, country, limit, work_type)
    ]

    excluded_cities = AMBIGUOUS_CITY_EXCLUSIONS.get(country.lower())
    if excluded_cities:
        per_source = {
            site: [j for j in rows if _city_of(j["location"]) not in excluded_cities]
            for site, rows in per_source.items()
        }

    print(f"[discovery] raw results per source: { {k: len(v) for k, v in per_source.items()} }")

    # Merge round-robin across sources instead of concatenating them in order —
    # otherwise a single reliable/prolific source (often LinkedIn, when others
    # are rate-limited) fills the entire result list before other sources that
    # DID return real jobs ever get a slot.
    merged: list[dict] = []
    queues = [list(v) for v in per_source.values() if v]
    while queues:
        for q in list(queues):
            merged.append(q.pop(0))
            if not q:
                queues.remove(q)

    jobs = [j for j in merged if _is_within_max_age(j)][:limit]

    if jobs:
        embeddings = embed_many([j["description"] or j["title"] for j in jobs])
        for j, e in zip(jobs, embeddings):
            j["embedding"] = e
    return jobs
