"""AI provider adapters with retry logic, connection pooling, and cross-provider fallback."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Per-request token accumulator ─────────────────────────────────────────────
# Holds a mutable list shared across all coroutines in the same gather() call
# (coroutines share context; asyncio.create_task() copies it, so task-based
# concurrency would need a different approach).
_token_accumulator: ContextVar[list[int] | None] = ContextVar(
    "_token_accumulator", default=None
)


def start_token_accumulation() -> tuple[list[int], Any]:
    """Start accumulating tokens. Returns (token_list, ctx_token)."""
    tokens: list[int] = []
    ctx_token = _token_accumulator.set(tokens)
    return tokens, ctx_token


def stop_token_accumulation(ctx_token: Any) -> None:
    """Restore the previous accumulator state."""
    _token_accumulator.reset(ctx_token)

# ── Shared connection pool ─────────────────────────────────────────────────────
# One AsyncClient for the whole process — avoids per-request TCP handshake
# overhead and exhausting OS file-descriptor limits under concurrency.
# Call close_http_client() in the FastAPI lifespan shutdown hook.
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=settings.ai_request_timeout_seconds,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )
    return _http_client


async def close_http_client() -> None:
    """Call this during application shutdown to drain the connection pool."""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


# ── Data classes ───────────────────────────────────────────────────────────────


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


# ── Providers ─────────────────────────────────────────────────────────────────


class BaseProvider:
    provider_name: str = "base"
    model_name: str = "base-model"

    async def generate(self, prompt: str, temperature: float = 0.7) -> ProviderResult:
        raise NotImplementedError

    def is_configured(self) -> bool:
        """Return True if this provider has the required credentials/config."""
        return False


class OpenAIProvider(BaseProvider):
    provider_name = "openai"

    def __init__(self) -> None:
        self.api_key = settings.openai_api_key
        self.model_name = settings.openai_model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def generate(self, prompt: str, temperature: float = 0.7) -> ProviderResult:
        if not self.api_key:
            raise ProviderError("Missing OPENAI_API_KEY", retriable=False)

        t0 = time.monotonic()
        client = _get_client()
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
            raise ProviderError("OpenAI rate limited", retriable=True)
        if resp.status_code >= 400:
            raise ProviderError(f"OpenAI upstream error: {resp.status_code}", retriable=False)

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise ProviderError("OpenAI response missing content", retriable=False)

        text = choices[0].get("message", {}).get("content", "")
        usage_data = data.get("usage", {})
        return ProviderResult(
            text=text,
            usage=ProviderUsage(
                provider=self.provider_name,
                model=self.model_name,
                prompt_tokens=usage_data.get("prompt_tokens"),
                completion_tokens=usage_data.get("completion_tokens"),
                total_tokens=usage_data.get("total_tokens"),
                latency_ms=latency,
            ),
        )


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

    def is_configured(self) -> bool:
        return bool(settings.ai_local_base_url)

    async def generate(self, prompt: str, temperature: float = 0.7) -> ProviderResult:
        if not settings.ai_local_base_url:
            raise ProviderError("Missing AI_LOCAL_BASE_URL", retriable=False)

        t0 = time.monotonic()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        client = _get_client()
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
            raise ProviderError("Local LLM rate limited", retriable=True)
        if resp.status_code >= 400:
            raise ProviderError(f"Local LLM upstream error: {resp.status_code}", retriable=False)

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise ProviderError("Local LLM response missing content", retriable=False)

        text = choices[0].get("message", {}).get("content", "")
        return ProviderResult(
            text=text,
            usage=ProviderUsage(
                provider=self.provider_name,
                model=self.model_name,
                latency_ms=latency,
            ),
        )


class GeminiProvider(BaseProvider):
    provider_name = "gemini"

    def __init__(self) -> None:
        self.gemini_api_key = settings.gemini_api_key
        self.model_name = settings.gemini_model

    def is_configured(self) -> bool:
        return bool(self.gemini_api_key)

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
        client = _get_client()
        try:
            resp = await client.post(url, json=body)
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            raise ProviderError(f"Gemini request failed: {e}", retriable=True)

        latency = int((time.monotonic() - t0) * 1000)

        if resp.status_code == 429:
            raise ProviderError("Gemini rate limited", retriable=True)
        if resp.status_code >= 400:
            raise ProviderError(f"Gemini upstream error: {resp.status_code}", retriable=False)

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise ProviderError("Gemini returned no candidates", retriable=False)

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise ProviderError("Gemini response missing text", retriable=False)

        text = parts[0].get("text", "")
        usage_meta = data.get("usageMetadata", {})
        return ProviderResult(
            text=text,
            usage=ProviderUsage(
                provider=self.provider_name,
                model=self.model_name,
                prompt_tokens=usage_meta.get("promptTokenCount"),
                completion_tokens=usage_meta.get("candidatesTokenCount"),
                total_tokens=usage_meta.get("totalTokenCount"),
                latency_ms=latency,
            ),
        )


class StubProvider(BaseProvider):
    """Deterministic provider for tests and explicit ``AI_PROVIDER=stub`` usage.

    When used as an *explicit* choice it returns a minimal valid JSON stub so
    the rest of the pipeline can proceed in CI/testing.  When it ends up in the
    fallback chain because *all real providers failed*, it raises a clear error
    instead of silently producing a broken game — that way the user sees an
    actionable message rather than a nonsensical result.
    """

    provider_name = "stub"
    model_name = "deterministic-local"

    def is_configured(self) -> bool:
        # Only advertise itself as configured when explicitly requested, so it
        # does NOT silently enter the auto fallback chain.
        return settings.ai_provider.lower() == "stub"

    async def generate(self, prompt: str, temperature: float = 0.7) -> ProviderResult:
        if settings.ai_provider.lower() != "stub":
            # We are here only because all real providers failed.
            raise ProviderError(
                "All AI providers failed and no fallback is available. "
                "Check your GEMINI_API_KEY / OPENAI_API_KEY / AI_LOCAL_BASE_URL configuration.",
                retriable=False,
            )
        text = '{"summary": "Stub response", "game_type": "arcade", "entities": ["Player"]}'
        return ProviderResult(
            text=text,
            usage=ProviderUsage(provider=self.provider_name, model=self.model_name),
        )


# ── Manager ────────────────────────────────────────────────────────────────────


class ProviderManager:
    def __init__(self) -> None:
        self._openai = OpenAIProvider()
        self._local = LocalOpenAICompatibleProvider()
        self._gemini = GeminiProvider()
        self._stub = StubProvider()

    def _select_primary(self) -> BaseProvider:
        pref = settings.ai_provider.lower()
        if pref == "openai":
            return self._openai
        if pref == "local":
            return self._local
        if pref == "gemini":
            return self._gemini
        if pref == "stub":
            return self._stub
        # auto: prefer gemini > openai > local > stub
        if settings.gemini_api_key:
            return self._gemini
        if settings.openai_api_key:
            return self._openai
        if settings.ai_local_base_url:
            return self._local
        return self._stub

    def _build_fallback_chain(self, primary: BaseProvider) -> list[BaseProvider]:
        """Return ordered list starting with primary, then other configured providers."""
        candidates: list[BaseProvider] = [
            self._gemini,
            self._openai,
            self._local,
            self._stub,
        ]
        # Put primary first, then the rest that are configured (excluding primary)
        chain: list[BaseProvider] = [primary]
        for p in candidates:
            if p is not primary and p.is_configured():
                chain.append(p)
        return chain

    async def generate(self, prompt: str, temperature: float = 0.7) -> ProviderResult:
        primary = self._select_primary()
        chain = self._build_fallback_chain(primary)
        last_error: Exception | None = None

        for provider in chain:
            for attempt in range(max(1, settings.ai_max_retries + 1)):
                try:
                    result = await provider.generate(prompt, temperature=temperature)
                    if attempt > 0 or provider is not primary:
                        logger.info(
                            "AI request succeeded via %s (attempt %d)",
                            provider.provider_name,
                            attempt + 1,
                        )
                    # Push tokens into the per-request accumulator if active.
                    acc = _token_accumulator.get(None)
                    if acc is not None and result.usage.total_tokens:
                        acc.append(result.usage.total_tokens)
                    return result
                except ProviderError as e:
                    last_error = e
                    if not e.retriable:
                        break  # Non-retriable — skip to next provider immediately
                    if attempt < settings.ai_max_retries:
                        await asyncio.sleep(random.uniform(1, 3))
                except (httpx.HTTPError, httpx.TimeoutException) as e:
                    last_error = e
                    if attempt < settings.ai_max_retries:
                        await asyncio.sleep(random.uniform(1, 3))
            else:
                # All retries for this provider exhausted — continue to next
                logger.warning(
                    "Provider %s exhausted retries, trying next", provider.provider_name
                )
                continue
            # Non-retriable error — try next provider
            logger.warning(
                "Provider %s non-retriable error: %s, trying next",
                provider.provider_name,
                last_error,
            )

        raise last_error or RuntimeError("All AI providers failed")


provider_manager = ProviderManager()
