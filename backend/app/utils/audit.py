"""Dedicated audit logger for security-critical events.

All security-relevant actions (logins, logouts, signup, file uploads, admin
actions, failures) are written to  logs/audit.log  independently of the
general application log.  This file is never mixed with debug output and is
retained for 90 days.

Usage::

    from app.utils.audit import audit_log

    audit_log("LOGIN_SUCCESS", username="alice", ip="10.0.0.1")
    audit_log("LOGIN_FAILURE", username="bob",  ip="10.0.0.2", reason="bad password")
"""

import logging
import logging.handlers
from pathlib import Path

_AUDIT_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "audit.log"

_fmt = logging.Formatter(
    "%(asctime)s | AUDIT | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)


def _build_audit_logger() -> logging.Logger:
    logger = logging.getLogger("sarvam.audit")
    if logger.handlers:
        return logger

    _AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(_AUDIT_LOG_PATH),
        when="midnight",
        interval=1,
        backupCount=90,
        encoding="utf-8",
        utc=True,
        delay=False,
    )
    handler.setFormatter(_fmt)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    # Do NOT propagate — audit events must not appear in the general log
    logger.propagate = False
    return logger


_audit_logger = _build_audit_logger()


def audit_log(event: str, **kwargs) -> None:
    """Write a structured audit entry.

    Args:
        event:   Short uppercase identifier, e.g. ``LOGIN_SUCCESS``.
        **kwargs: Arbitrary key=value pairs included in the log line.
    """
    parts = [f"event={event}"]
    parts += [f"{k}={v}" for k, v in kwargs.items()]
    _audit_logger.info(" | ".join(parts))
