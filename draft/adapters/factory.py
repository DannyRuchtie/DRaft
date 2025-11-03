"""Factory helpers for loading LLM adapters."""

from __future__ import annotations

from ..config import DraftConfig
from ..util import env_first
from . import Adapter, AdapterError
from .anthropic import AnthropicAdapter
from .google import GoogleAdapter
from .ollama import OllamaAdapter
from .openai import OpenAIAdapter


def build_adapter(config: DraftConfig) -> Adapter:
    """Instantiate an adapter based on configuration."""
    provider = config.provider.lower()
    if provider == "ollama":
        return OllamaAdapter(model=config.model)
    if provider == "openai":
        api_key = env_first("OPENAI_API_KEY")
        if not api_key:
            raise AdapterError("OPENAI_API_KEY is not set.")
        return OpenAIAdapter(model=config.model, api_key=api_key)
    if provider == "anthropic":
        api_key = env_first("ANTHROPIC_API_KEY")
        if not api_key:
            raise AdapterError("ANTHROPIC_API_KEY is not set.")
        return AnthropicAdapter(model=config.model, api_key=api_key)
    if provider == "google":
        api_key = env_first("GOOGLE_API_KEY")
        if not api_key:
            raise AdapterError("GOOGLE_API_KEY is not set.")
        return GoogleAdapter(model=config.model, api_key=api_key)
    raise AdapterError(f"Unsupported provider: {config.provider}")
