"""Centralised logging configuration for Sarvam AI backend.

Call `setup_logging()` once at startup (in main.py).  All modules can then
use the standard `logging.getLogger(__name__)` pattern and their output will
automatically flow through this configuration.

Log files are written to  <repo_root>/backend/logs/  and rotated daily,
keeping 30 days of history.  Console output mirrors the file at the configured
level so the terminal still shows live activity.
"""

import logging
import logging.handlers
import os
from pathlib import Path

# ── Configuration (override with env vars) ────────────────────────────────
_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
_LOG_LEVEL_STR = os.environ.get("LOG_LEVEL", "INFO").upper()
_LOG_LEVEL = getattr(logging, _LOG_LEVEL_STR, logging.INFO)

_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> None:
    """Configure root logger with rotating file handler + coloured console."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()

    # Check if our file handler is already attached (avoids duplicate handlers
    # on hot-reload), but do NOT skip setup just because Uvicorn has added its
    # own handlers first — that was causing log files to stay empty.
    already_has_file_handler = any(
        isinstance(h, logging.handlers.TimedRotatingFileHandler)
        for h in root.handlers
    )
    if already_has_file_handler:
        return

    root.setLevel(_LOG_LEVEL)
    formatter = logging.Formatter(_FMT, datefmt=_DATE_FMT)

    # ── Daily rotating file handler ────────────────────────────────────────
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(_LOG_DIR / "servam.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=True,
        delay=False,
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(_LOG_LEVEL)
    root.addHandler(file_handler)

    # Always ensure the root logger level is correct even if Uvicorn lowered it
    root.setLevel(_LOG_LEVEL)

    # Separate error-only log for quick triage
    error_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(_LOG_DIR / "errors.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=True,
        delay=False,
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    root.addHandler(error_handler)

    # ── Console handler ────────────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(_LOG_LEVEL)
    root.addHandler(console_handler)

    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "chromadb.telemetry", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging initialised — level=%s  dir=%s", _LOG_LEVEL_STR, _LOG_DIR
    )
