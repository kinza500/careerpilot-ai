"""LLM abstraction.

Confidentiality drives the choice of provider: candidate resumes are processed
via a provider that does not train on API data. OpenAI (default), Anthropic, and
local Ollama all satisfy this on their API/local paths — unlike free public chat
tiers, which may train on submissions. For a fully local / air-gapped
deployment, set LLM_PROVIDER=ollama and no CV text ever leaves the host.
"""
from __future__ import annotations

import json

from app.config import get_settings

settings = get_settings()


class LLM:
    """Minimal chat interface: `.complete(system, user)` -> str."""

    def complete(self, system: str, user: str, max_tokens: int = 2000, model: str | None = None) -> str:
        raise NotImplementedError

    def complete_json(self, system: str, user: str, max_tokens: int = 2000, model: str | None = None) -> dict:
        raw = self.complete(system + "\nRespond with ONLY valid JSON, no prose, no markdown fences.",
                            user, max_tokens, model)
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(raw)

    def chat(self, system: str, messages: list[dict], max_tokens: int = 2000, model: str | None = None) -> str:
        """Multi-turn variant for conversational agents (e.g. mock interviews)
        that need the full running exchange, not just one system+user turn."""
        raise NotImplementedError


class OpenAILLM(LLM):
    def __init__(self) -> None:
        from openai import OpenAI
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    def complete(self, system: str, user: str, max_tokens: int = 2000, model: str | None = None) -> str:
        return self.chat(system, [{"role": "user", "content": user}], max_tokens, model)

    def chat(self, system: str, messages: list[dict], max_tokens: int = 2000, model: str | None = None) -> str:
        # NOTE: gpt-4.1 / gpt-4o accept `max_tokens`. If you switch to a gpt-5 /
        # o-series reasoning model, rename this to `max_completion_tokens`.
        resp = self.client.chat.completions.create(
            model=model or self.model,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, *messages],
        )
        return resp.choices[0].message.content or ""


class AnthropicLLM(LLM):
    def __init__(self) -> None:
        import anthropic
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    def complete(self, system: str, user: str, max_tokens: int = 2000, model: str | None = None) -> str:
        return self.chat(system, [{"role": "user", "content": user}], max_tokens, model)

    def chat(self, system: str, messages: list[dict], max_tokens: int = 2000, model: str | None = None) -> str:
        msg = self.client.messages.create(
            model=model or self.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")


class OllamaLLM(LLM):
    def __init__(self) -> None:
        import httpx
        self.http = httpx.Client(base_url=settings.ollama_base_url, timeout=120)
        self.model = settings.ollama_model

    def complete(self, system: str, user: str, max_tokens: int = 2000, model: str | None = None) -> str:
        return self.chat(system, [{"role": "user", "content": user}], max_tokens, model)

    def chat(self, system: str, messages: list[dict], max_tokens: int = 2000, model: str | None = None) -> str:
        r = self.http.post("/api/chat", json={
            "model": model or self.model,
            "stream": False,
            "options": {"num_predict": max_tokens},
            "messages": [{"role": "system", "content": system}, *messages],
        })
        r.raise_for_status()
        return r.json()["message"]["content"]


def get_llm() -> LLM:
    provider = settings.llm_provider
    if provider == "ollama":
        return OllamaLLM()
    if provider == "anthropic":
        return AnthropicLLM()
    return OpenAILLM()
