"""Base agent that all specialised agents extend.

Wraps the shared ``provider_manager`` so every agent gets:
- A single async ``generate()`` call
- Consistent JSON extraction with graceful fallback
- The same retry / provider-switching logic already in ProviderManager
"""
from __future__ import annotations

import json
import re
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
        """Strip markdown fences and parse the first complete JSON object.

        Uses an iterative bracket-depth scan rather than recursion or rfind so
        that text containing multiple JSON objects (e.g. preamble + real payload)
        always yields the *first* well-formed object, and deep/malformed LLM
        responses cannot cause a stack overflow.
        """
        text = text.strip()

        # Remove markdown code fences (```json ... ``` or ``` ... ```)
        if text.startswith("```"):
            lines = [l for l in text.splitlines() if not l.startswith("```")]
            text = "\n".join(lines).strip()

        # Fast path: the whole text is valid JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Iterative bracket-depth scan: try every '{' until we find a
        # well-formed JSON object (handles malformed preamble objects).
        search_from = 0
        while True:
            start = text.find("{", search_from)
            if start == -1:
                return {}

            depth = 0
            in_string = False
            escape_next = False
            end = -1

            for i, ch in enumerate(text[start:], start=start):
                if escape_next:
                    escape_next = False
                    continue
                if ch == "\\" and in_string:
                    escape_next = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break

            if end == -1:
                # No matching closing brace found at all
                return {}

            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                # This object was malformed — advance past it and try the next
                search_from = end + 1
