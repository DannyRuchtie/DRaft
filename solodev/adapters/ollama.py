"""Ollama provider adapter."""

from __future__ import annotations

from typing import Any

import requests
from requests import Response

from . import Adapter, AdapterError, LLMRequest


class OllamaAdapter(Adapter):
    """Interact with a local Ollama model server."""

    def __init__(self, model: str, host: str = "http://localhost:11434") -> None:
        self.model = model
        self.host = host.rstrip("/")

    def generate(self, request: LLMRequest) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": request.prompt,
            "stream": False,
        }
        if request.system:
            payload["system"] = request.system

        try:
            response: Response = requests.post(f"{self.host}/api/generate", json=payload, timeout=60)
            response.raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - network errors
            raise AdapterError(f"Ollama request failed: {exc}") from exc

        data = response.json()
        text = data.get("response")
        if not text:
            raise AdapterError("Ollama response missing 'response' field.")
        return text
