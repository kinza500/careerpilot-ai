"""FastAPI entrypoint."""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.routers import applications, auth, interview, jobs, resumes

settings = get_settings()

# Never log request bodies — they can contain resume text.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
app = FastAPI(title=settings.app_name, version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(resumes.router)
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(interview.router)


@app.on_event("startup")
async def _preload_embedding_model():
    # Only the fully local/air-gapped path (LLM_PROVIDER=ollama) loads a local
    # sentence-transformers model at all; the default path uses OpenAI's
    # embeddings API and has nothing to preload. Loading it once at boot
    # instead of on the first request avoids paying that cost (15-40s on a
    # slow shared CPU) inside a user's actual first request.
    from app.agents.embeddings import _use_local, _local_model
    if _use_local():
        _local_model()


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name, "llm": settings.llm_provider}


@app.exception_handler(RuntimeError)
async def runtime_handler(_: Request, exc: RuntimeError):
    return JSONResponse(status_code=500, content={"detail": str(exc)})
