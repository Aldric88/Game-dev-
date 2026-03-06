"""AI provider adapters with retry logic and provider switching."""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings


@dataclass
class ProviderUsage:
    provider: str = ""
    model: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int = 0
    retries: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "retries": self.retries,
        }


@dataclass
class ProviderResult:
    text: str
    usage: ProviderUsage


class ProviderError(RuntimeError):
    def __init__(self, message: str, retriable: bool = False):
        super().__init__(message)
        self.retriable = retriable


class BaseProvider:
    provider_name: str = "base"
    model_name: str = "base-model"

    async def generate(self, prompt: str, temperature: float = 0.7) -> ProviderResult:
        raise NotImplementedError


class OpenAIProvider(BaseProvider):
    provider_name = "openai"

    def __init__(self) -> None:
        self.api_key = settings.openai_api_key
        self.model_name = settings.openai_model

    async def generate(self, prompt: str, temperature: float = 0.7) -> ProviderResult:
        if not self.api_key:
            raise ProviderError("Missing OPENAI_API_KEY", retriable=False)

        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=settings.ai_request_timeout_seconds) as client:
            try:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature,
                    },
                )
            except (httpx.TimeoutException, httpx.HTTPError) as e:
                raise ProviderError(f"OpenAI request failed: {e}", retriable=True)

        latency = int((time.monotonic() - t0) * 1000)

        if resp.status_code == 429:
            raise ProviderError("OpenAI rate limited request", retriable=True)
        if resp.status_code >= 400:
            raise ProviderError(f"OpenAI upstream error: {resp.status_code}", retriable=False)

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise ProviderError("OpenAI response missing assistant content", retriable=False)

        text = choices[0].get("message", {}).get("content", "")
        usage_data = data.get("usage", {})
        usage = ProviderUsage(
            provider=self.provider_name,
            model=self.model_name,
            prompt_tokens=usage_data.get("prompt_tokens"),
            completion_tokens=usage_data.get("completion_tokens"),
            total_tokens=usage_data.get("total_tokens"),
            latency_ms=latency,
        )
        return ProviderResult(text=text, usage=usage)


class LocalOpenAICompatibleProvider(BaseProvider):
    provider_name = "local"

    def __init__(self) -> None:
        base_url = settings.ai_local_base_url.strip().rstrip("/")
        self.model_name = settings.ai_local_model
        self.api_key = settings.ai_local_api_key

        if base_url.endswith("/chat/completions"):
            self._endpoint = base_url
        elif base_url.endswith("/v1"):
            self._endpoint = base_url + "/chat/completions"
        else:
            self._endpoint = base_url + "/v1/chat/completions"

    async def generate(self, prompt: str, temperature: float = 0.7) -> ProviderResult:
        if not settings.ai_local_base_url:
            raise ProviderError("Missing AI_LOCAL_BASE_URL", retriable=False)

        t0 = time.monotonic()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=settings.ai_request_timeout_seconds) as client:
            try:
                resp = await client.post(
                    self._endpoint,
                    headers=headers,
                    json={
                        "model": self.model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature,
                    },
                )
            except (httpx.TimeoutException, httpx.HTTPError) as e:
                raise ProviderError(f"Local LLM request failed: {e}", retriable=True)

        latency = int((time.monotonic() - t0) * 1000)

        if resp.status_code == 429:
            raise ProviderError("Local LLM rate limited request", retriable=True)
        if resp.status_code >= 400:
            raise ProviderError(f"Local LLM upstream error: {resp.status_code}", retriable=False)

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise ProviderError("Local LLM response missing assistant content", retriable=False)

        text = choices[0].get("message", {}).get("content", "")
        usage = ProviderUsage(
            provider=self.provider_name,
            model=self.model_name,
            latency_ms=latency,
        )
        return ProviderResult(text=text, usage=usage)


class GeminiProvider(BaseProvider):
    provider_name = "gemini"

    def __init__(self) -> None:
        self.gemini_api_key = settings.gemini_api_key
        self.model_name = settings.gemini_model

    async def generate(self, prompt: str, temperature: float = 0.7) -> ProviderResult:
        if not self.gemini_api_key:
            raise ProviderError("Missing GEMINI_API_KEY", retriable=False)

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_name}:generateContent?key={self.gemini_api_key}"
        )
        body = {
            "contents": [{"parts": [{"text": f"\nUser request:\n\n{prompt}"}]}],
            "generationConfig": {"temperature": temperature},
        }

        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=settings.ai_request_timeout_seconds) as client:
            try:
                resp = await client.post(url, json=body)
            except (httpx.TimeoutException, httpx.HTTPError) as e:
                raise ProviderError(f"Gemini request failed: {e}", retriable=True)

        latency = int((time.monotonic() - t0) * 1000)

        if resp.status_code == 429:
            raise ProviderError("Gemini rate limited request", retriable=True)
        if resp.status_code >= 400:
            raise ProviderError(f"Gemini upstream error: {resp.status_code}", retriable=False)

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise ProviderError("Gemini returned no candidates", retriable=False)

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise ProviderError("Gemini response missing generated text", retriable=False)

        text = parts[0].get("text", "")
        usage_meta = data.get("usageMetadata", {})
        usage = ProviderUsage(
            provider=self.provider_name,
            model=self.model_name,
            prompt_tokens=usage_meta.get("promptTokenCount"),
            completion_tokens=usage_meta.get("candidatesTokenCount"),
            total_tokens=usage_meta.get("totalTokenCount"),
            latency_ms=latency,
        )
        return ProviderResult(text=text, usage=usage)


class StubProvider(BaseProvider):
    provider_name = "stub"
    model_name = "deterministic-local"

    async def generate(self, prompt: str, temperature: float = 0.7) -> ProviderResult:
        text = '{"summary": "Stub response", "game_type": "arcade", "entities": ["Player"]}'
        return ProviderResult(
            text=text,
            usage=ProviderUsage(provider=self.provider_name, model=self.model_name),
        )


class ProviderManager:
    def __init__(self) -> None:
        self._openai = OpenAIProvider()
        self._local = LocalOpenAICompatibleProvider()
        self._gemini = GeminiProvider()
        self._stub = StubProvider()

    def _select_provider(self) -> BaseProvider:
        pref = settings.ai_provider.lower()
        if pref == "openai":
            return self._openai
        if pref == "local":
            return self._local
        if pref == "gemini":
            return self._gemini
        if pref == "stub":
            return self._stub
        # auto: prefer gemini if key set, else openai, else local, else stub
        if settings.gemini_api_key:
            return self._gemini
        if settings.openai_api_key:
            return self._openai
        if settings.ai_local_base_url:
            return self._local
        return self._stub

    async def generate(self, prompt: str, temperature: float = 0.7) -> ProviderResult:
        provider = self._select_provider()
        last_error: Exception | None = None
        for attempt in range(max(1, settings.ai_max_retries + 1)):
            try:
                return await provider.generate(prompt, temperature=temperature)
            except ProviderError as e:
                last_error = e
                if not e.retriable:
                    break
                if attempt < settings.ai_max_retries:
                    await asyncio.sleep(random.uniform(1, 3))
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                last_error = e
                if attempt < settings.ai_max_retries:
                    await asyncio.sleep(random.uniform(1, 3))
        raise last_error or RuntimeError("AI provider failed")


provider_manager = ProviderManager()
