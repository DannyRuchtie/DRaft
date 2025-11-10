"""Model provider adapters for SoloDev."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class LLMRequest:
    prompt: str
    system: str | None = None


class AdapterError(RuntimeError):
    """Raised when a provider interaction fails."""


class Adapter(Protocol):
    """Common protocol for provider adapters."""

    def generate(self, request: LLMRequest) -> str:
        ...
