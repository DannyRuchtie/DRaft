"""Anthropic provider adapter."""

from __future__ import annotations

from typing import Any

import requests

from . import Adapter, AdapterError, LLMRequest

ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"


class AnthropicAdapter(Adapter):
    """Interact with the Anthropic Messages API."""

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self.api_key = api_key

    def generate(self, request: LLMRequest) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system:
            payload["system"] = request.system

        try:
            response = requests.post(ANTHROPIC_ENDPOINT, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - network errors
            raise AdapterError(f"Anthropic request failed: {exc}") from exc

        data = response.json()
        content = data.get("content", [])
        if not content:
            raise AdapterError("Anthropic response missing content.")
        first = content[0]
        if isinstance(first, dict):
            text = first.get("text")
            if text:
                return text
        raise AdapterError("Anthropic response format unexpected.")
