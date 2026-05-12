"""Analytics event tracking utility — lightweight, non-blocking."""

import logging
import threading

log = logging.getLogger(__name__)


def track_message(user_id: str | None, agent_type: str, message: str) -> None:
    """Fire-and-forget: log a message event to analytics_events."""
    def _write():
        try:
            from app.database import log_analytics_event
            log_analytics_event(user_id=user_id, agent_type=agent_type, message_len=len(message))
        except Exception as exc:
            log.debug("Analytics tracking failed (non-fatal): %s", exc)
    threading.Thread(target=_write, daemon=True).start()
