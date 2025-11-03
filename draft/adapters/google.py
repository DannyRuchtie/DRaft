"""Google Gemini provider adapter."""

from __future__ import annotations

from typing import Any

import requests

from . import Adapter, AdapterError, LLMRequest

GOOGLE_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GoogleAdapter(Adapter):
    """Interact with the Google Gemini API."""

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self.api_key = api_key

    def generate(self, request: LLMRequest) -> str:
        params = {"key": self.api_key}
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": request.prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        if request.system:
            payload["systemInstruction"] = {"parts": [{"text": request.system}]}

        endpoint = GOOGLE_ENDPOINT.format(model=self.model)
        try:
            response = requests.post(endpoint, params=params, json=payload, timeout=60)
            response.raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - network errors
            raise AdapterError(f"Google Gemini request failed: {exc}") from exc

        data = response.json()
        candidates = data.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if parts:
                text = parts[0].get("text")
                if text:
                    return text
        raise AdapterError("Google Gemini response missing text.")
