"""Celery worker for long-running agent jobs (job discovery, application prep).

For the MVP the routers call the pipeline synchronously; this worker exists so
heavier runs can be offloaded without changing the agent code. Wire endpoints to
`.delay(...)` when you need async execution + progress via WebSocket/SSE.
"""
from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery("careerpilot", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_track_started = True


@celery_app.task
def discover_task(user_id: str, query: str, location: str | None, limit: int) -> dict:
    # EXTENSION POINT: mirror routers/jobs.discover_and_rank here for async runs.
    from app.agents import discovery_agent
    jobs = discovery_agent.discover_jobs(query, location, limit)
    return {"count": len(jobs)}
