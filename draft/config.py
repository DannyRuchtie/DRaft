"""Configuration handling for DRaft."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml

from .util import deep_merge, parse_duration

CONFIG_FILENAME = ".draft.yml"

DEFAULT_CONFIG: dict[str, Any] = {
    "mode": "push",
    "branch": "auto/${USER}",
    "idle": "30s",
    "batch_window": "5m",
    "secret_scan": True,
    "ci_default": "skip",
    "smart_push": {
        "ask": True,
        "max_diff_lines": 1000,
        "respect_protected": True,
        "default_skip_ci": True,
    },
    "provider": "ollama",
    "model": "qwen2.5-coder:14b",
    "log_level": "INFO",
    "snapshot_max_size": 10485760,  # 10 MB
    "secret_patterns": [],
    "protected_branches": ["main", "master", "production"],
}


class ConfigError(Exception):
    """Raised when configuration could not be loaded or parsed."""


@dataclass(frozen=True)
class SmartPushConfig:
    ask: bool = True
    max_diff_lines: int = 1000
    respect_protected: bool = True
    default_skip_ci: bool = True


@dataclass(frozen=True)
class DraftConfig:
    mode: str = DEFAULT_CONFIG["mode"]
    branch: str = DEFAULT_CONFIG["branch"]
    idle: str = DEFAULT_CONFIG["idle"]
    batch_window: str = DEFAULT_CONFIG["batch_window"]
    secret_scan: bool = DEFAULT_CONFIG["secret_scan"]
    ci_default: str = DEFAULT_CONFIG["ci_default"]
    smart_push: SmartPushConfig = field(default_factory=SmartPushConfig)
    provider: str = DEFAULT_CONFIG["provider"]
    model: str = DEFAULT_CONFIG["model"]
    log_level: str = DEFAULT_CONFIG["log_level"]
    snapshot_max_size: int = DEFAULT_CONFIG["snapshot_max_size"]
    secret_patterns: list[str] = field(default_factory=list)
    protected_branches: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DraftConfig":
        """Construct from a dictionary, applying defaults for missing keys."""
        merged = deep_merge(DEFAULT_CONFIG, data)
        smart_push = merged.get("smart_push", {})
        smart_push_cfg = SmartPushConfig(
            ask=bool(smart_push.get("ask", True)),
            max_diff_lines=int(smart_push.get("max_diff_lines", 1000)),
            respect_protected=bool(smart_push.get("respect_protected", True)),
            default_skip_ci=bool(smart_push.get("default_skip_ci", True)),
        )
        return cls(
            mode=str(merged.get("mode")),
            branch=str(merged.get("branch")),
            idle=str(merged.get("idle")),
            batch_window=str(merged.get("batch_window")),
            secret_scan=bool(merged.get("secret_scan")),
            ci_default=str(merged.get("ci_default")),
            smart_push=smart_push_cfg,
            provider=str(merged.get("provider")),
            model=str(merged.get("model")),
            log_level=str(merged.get("log_level", "INFO")),
            snapshot_max_size=int(merged.get("snapshot_max_size", 10485760)),
            secret_patterns=list(merged.get("secret_patterns", [])),
            protected_branches=list(merged.get("protected_branches", [])),
            raw=merged,
        )

    @property
    def idle_duration(self) -> timedelta:
        """Return the configured idle duration as a timedelta."""
        return parse_duration(self.idle)

    @property
    def batch_window_duration(self) -> timedelta:
        """Return the configured batch window as a timedelta."""
        return parse_duration(self.batch_window)


def load_config(path: Path | None = None) -> DraftConfig:
    """Load configuration from a file, applying defaults when missing."""
    config_path = path or Path(CONFIG_FILENAME)
    if not config_path.exists():
        return DraftConfig()

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - depends on broken input
        raise ConfigError(f"Invalid YAML in {config_path}") from exc

    if not isinstance(payload, dict):
        raise ConfigError("Configuration root must be a mapping.")

    return DraftConfig.from_dict(payload)


def save_config(config: DraftConfig, path: Path | None = None) -> None:
    """Write configuration back to disk."""
    config_path = path or Path(CONFIG_FILENAME)
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config.raw or DEFAULT_CONFIG, handle, sort_keys=False)
