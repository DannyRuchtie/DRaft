"""Lightweight status API server for editor integrations."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

from .cycle import CycleReport


@dataclass
class StatusStore:
    """Thread-safe store for the latest cycle report."""

    _data: Dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def update(self, report: CycleReport) -> None:
        snapshot = {
            "status": report.status,
            "message": report.message,
            "commits": report.commits,
            "tag": report.tag,
            "pushed": report.pushed,
            "branch": report.branch,
            "plan_source": report.plan.source,
            "groups": [group.to_dict() for group in report.plan.groups],
            "policy": [{"severity": msg.severity, "message": msg.message} for msg in report.policy.messages],
        }
        with self._lock:
            self._data = snapshot

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data)


class StatusRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler serving the latest cycle status."""

    server_version = "SoloDevStatus/1.0"

    def do_GET(self) -> None:
        if self.path not in {"/", "/status"}:
            self.send_response(404)
            self.end_headers()
            return

        payload = self.server.store.snapshot()  # type: ignore[attr-defined]
        body = json.dumps(payload or {"status": "idle"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - inherited signature
        return  # Silence default logging


class SoloDevStatusHTTPServer(ThreadingHTTPServer):
    """Custom HTTP server carrying the shared status store."""

    def __init__(self, server_address, RequestHandlerClass, store: StatusStore):
        super().__init__(server_address, RequestHandlerClass)
        self.store = store


class StatusServer:
    """Lifecycle manager for the threaded HTTP server."""

    def __init__(self, port: int, store: StatusStore) -> None:
        self.store = store
        self._server = SoloDevStatusHTTPServer(("", port), StatusRequestHandler, store)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


def serve_status(store: StatusStore | None = None, port: int = 0) -> StatusServer:
    """Start a lightweight status server for editor integrations."""
    status_store = store or StatusStore()
    server = StatusServer(port=port, store=status_store)
    server.start()
    return server
