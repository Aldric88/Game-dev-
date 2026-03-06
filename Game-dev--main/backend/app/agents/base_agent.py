"""Base agent that all specialised agents extend.

Wraps the shared ``provider_manager`` so every agent gets:
- A single async ``generate()`` call
- Consistent JSON extraction with graceful fallback
- The same retry / provider-switching logic already in ProviderManager
"""
from __future__ import annotations

import json
from typing import Any

from app.services.ai_providers import ProviderUsage, provider_manager


class BaseAgent:
    """Thin base class for all game-generation agents."""

    temperature: float = 0.7

    async def generate(self, prompt: str, temperature: float | None = None) -> str:
        """Call the configured AI provider and return raw text."""
        result = await provider_manager.generate(
            prompt, temperature=temperature or self.temperature
        )
        return result.text

    def extract_json(self, text: str) -> dict[str, Any]:
        """Strip markdown fences and parse the first JSON object found."""
        text = text.strip()
        # Remove markdown fences
        if text.startswith("```"):
            lines = text.splitlines()
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find first { ... } block
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        return {}
