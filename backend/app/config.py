"""Central configuration. All secrets come from environment variables so the
same image runs unchanged in docker-compose and on Render/Supabase."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Core ---
    app_name: str = "CareerPilot AI"
    environment: str = "development"
    # asyncpg URL, e.g. postgresql+asyncpg://careerpilot_app:pw@db:5432/careerpilot
    database_url: str = "postgresql+asyncpg://careerpilot_app:app_pw_change_me@db:5432/careerpilot"

    # --- Auth ---
    jwt_secret: str = "change-me-in-prod-please-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 1 day

    # --- Confidentiality ---
    # Base64 urlsafe 32-byte key for Fernet (CV encryption at rest).
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    cv_encryption_key: str = ""

    # --- LLM ---
    # Provider that does NOT train on customer data is required for confidential
    # CVs. OpenAI, Anthropic, and Ollama all satisfy this on the API/local path
    # (unlike free consumer chat tiers).
    llm_provider: str = "openai"             # openai | anthropic | ollama
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1"            # or gpt-5.1 / gpt-5.5 for more capability
    # Interview practice tolerates a cheaper/faster model than cover letters —
    # conversational Q&A + feedback doesn't need top-tier reasoning depth.
    openai_interview_model: str = "gpt-4.1-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # --- Embeddings (local sentence-transformers keeps CV text on our own box) ---
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Background jobs ---
    redis_url: str = "redis://redis:6379/0"

    # --- CORS ---
    frontend_origin: str = "http://localhost:3000"

    # --- Company research (Tavily: search API built for agents; ZDR available) ---
    tavily_api_key: str = ""

    # --- Extra job aggregator (fills gaps where JobSpy's scrapers have no
    # coverage or get blocked, e.g. Pakistan/Gulf) ---
    jooble_api_key: str = ""

    # --- SerpApi's Google Jobs engine (licensed access to Google's own job
    # index, which itself aggregates postings from many boards Google
    # indexes) — a supplemental source, not a bypass of any blocked site. ---
    serpapi_key: str = ""

    # --- Gmail draft integration (gmail.compose scope only; never sends) ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
