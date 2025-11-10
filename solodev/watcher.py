"""Filesystem watcher that triggers SoloDev cycles."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .config import SoloDevConfig
from .cycle import CycleManager, CycleReport
from .ext_api import StatusStore


def _should_ignore(path: Path) -> bool:
    """
    Check if a path should be ignored by the watcher.
    
    Args:
        path: File path to check
        
    Returns:
        True if path should be ignored (e.g., inside .git directory)
    """
    parts = path.parts
    # Ignore anything in .git directories
    return any(part.startswith(".git") for part in parts)


class SoloDevEventHandler(FileSystemEventHandler):
    """
    File system event handler for the SoloDev watcher.
    
    Filters events and triggers the cycle callback when relevant files change.
    """

    def __init__(self, callback: Callable[[], None]) -> None:
        """
        Initialize the event handler.
        
        Args:
            callback: Function to call when a relevant file event occurs
        """
        super().__init__()
        self.callback = callback

    def on_any_event(self, event: FileSystemEvent) -> None:
        """
        Handle filesystem events.
        
        Filters out directory events and ignored paths, then triggers callback.
        
        Args:
            event: Filesystem event from watchdog
        """
        # Ignore directory changes (we only care about files)
        if event.is_directory:
            return
        # Ignore .git directory and other excluded paths
        if _should_ignore(Path(event.src_path)):
            return
        # Trigger cycle scheduling
        self.callback()


class CycleWatcher:
    """
    Coordinate filesystem events with cycle execution.
    
    The watcher monitors a directory tree for changes and orchestrates
    SoloDev cycles with intelligent debouncing and batch windows.
    """

    def __init__(
        self,
        root: Path,
        config: SoloDevConfig,
        manager: CycleManager,
        status_store: StatusStore,
        ask_push: Callable[[CycleReport], bool] | None = None,
    ) -> None:
        """
        Initialize the cycle watcher.
        
        Args:
            root: Root directory to watch
            config: SoloDev configuration
            manager: Cycle manager instance
            status_store: Status store for API reporting
            ask_push: Optional callback to confirm pushes
        """
        self.root = root
        self.config = config
        self.manager = manager
        self.status_store = status_store
        self.ask_push = ask_push

        # Watchdog observer for filesystem events
        self._observer = Observer()
        # Timer for debouncing (idle window)
        self._timer: threading.Timer | None = None
        # Lock for thread-safe timer management
        self._lock = threading.Lock()
        # Track last cycle time to enforce batch window
        self._last_cycle_monotonic: float = 0.0

    def start(self) -> None:
        """
        Start watching the filesystem.
        
        Creates an event handler and begins monitoring the root directory
        recursively for file changes.
        """
        handler = SoloDevEventHandler(self._schedule)
        self._observer.schedule(handler, str(self.root), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        """
        Stop watching the filesystem.
        
        Cancels any pending timers and shuts down the observer thread.
        """
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
        self._observer.stop()
        self._observer.join(timeout=2)

    # Internal ---------------------------------------------------------------------

    def _schedule(self) -> None:
        """
        Schedule a cycle to run after the idle duration.
        
        Cancels any existing timer and starts a new one. This implements
        debouncing: the timer resets on each file change.
        """
        delay = self.config.idle_duration.total_seconds()
        with self._lock:
            # Cancel existing timer if any (reset debounce)
            if self._timer:
                self._timer.cancel()
            # Schedule new cycle attempt
            self._timer = threading.Timer(delay, self._maybe_run_cycle)
            self._timer.daemon = True
            self._timer.start()

    def _maybe_run_cycle(self) -> None:
        """
        Attempt to run a cycle, respecting the batch window.
        
        If the batch window hasn't elapsed since the last cycle,
        reschedules instead of running immediately. This prevents
        excessive cycles during continuous editing.
        """
        with self._lock:
            self._timer = None
            now = time.monotonic()
            window = self.config.batch_window_duration.total_seconds()
            
            # Check if batch window has elapsed since last cycle
            if self._last_cycle_monotonic and (now - self._last_cycle_monotonic) < window:
                # Too soon - reschedule for later
                delay = max(window - (now - self._last_cycle_monotonic), self.config.idle_duration.total_seconds())
                self._timer = threading.Timer(delay, self._maybe_run_cycle)
                self._timer.daemon = True
                self._timer.start()
                return
            
            # Batch window elapsed - mark cycle time
            self._last_cycle_monotonic = now

        # Execute cycle (outside lock to avoid blocking file events)
        report = self.manager.execute(mode=self.config.mode, ask_push=self.ask_push)
        # Update status for API consumers
        self.status_store.update(report)
