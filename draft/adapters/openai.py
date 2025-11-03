"""OpenAI provider adapter."""

from __future__ import annotations

from typing import Any

import requests

from . import Adapter, AdapterError, LLMRequest

OPENAI_ENDPOINT = "https://api.openai.com/v1/responses"


class OpenAIAdapter(Adapter):
    """Interact with the OpenAI Responses API."""

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self.api_key = api_key

    def generate(self, request: LLMRequest) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "input": request.prompt,
            "response_format": {"type": "json_object"},
        }
        if request.system:
            payload["metadata"] = {"system": request.system}

        try:
            response = requests.post(OPENAI_ENDPOINT, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - network errors
            raise AdapterError(f"OpenAI request failed: {exc}") from exc

        data = response.json()
        output = data.get("output", [])
        if not output:
            raise AdapterError("OpenAI response missing 'output' field.")
        first = output[0]
        if isinstance(first, dict):
            text = first.get("content")
            if isinstance(text, list) and text:
                return text[0].get("text", "")
            if isinstance(text, str):
                return text
        raise AdapterError("OpenAI response format unexpected.")
