"""Centralized logging configuration for DRaft."""

from __future__ import annotations

import logging
import sys
from typing import Optional

# Define log levels
LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


def setup_logging(level: str = "INFO", verbose: int = 0, quiet: bool = False) -> logging.Logger:
    """
    Configure logging for DRaft.
    
    Args:
        level: Base log level (DEBUG, INFO, WARNING, ERROR)
        verbose: Verbosity increment (each level decreases threshold)
        quiet: If True, only show errors
        
    Returns:
        Configured logger instance
    """
    # Determine effective level
    if quiet:
        effective_level = logging.ERROR
    elif verbose == 1:
        effective_level = logging.INFO
    elif verbose >= 2:
        effective_level = logging.DEBUG
    else:
        effective_level = LEVELS.get(level.upper(), logging.INFO)
    
    # Configure root logger
    logger = logging.getLogger("draft")
    logger.setLevel(effective_level)
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(effective_level)
    
    # Create formatter
    if effective_level <= logging.DEBUG:
        # Detailed format for debug mode
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    else:
        # Simple format for normal mode
        formatter = logging.Formatter("%(levelname)-8s %(message)s")
    
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (defaults to 'draft')
        
    Returns:
        Logger instance
    """
    if name:
        return logging.getLogger(f"draft.{name}")
    return logging.getLogger("draft")

