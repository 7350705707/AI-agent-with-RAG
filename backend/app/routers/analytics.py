"""Analytics controller — usage statistics for admin and per-user views."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, require_admin
from app.database import get_analytics_summary, get_user_analytics

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary")
def api_analytics_summary(_admin: dict = Depends(require_admin)):
    """Platform-wide analytics — admin only."""
    try:
        return get_analytics_summary()
    except Exception as exc:
        log.error("Failed to fetch analytics summary: %s", exc, exc_info=True)
        raise HTTPException(500, "Failed to retrieve analytics")


@router.get("/me")
def api_my_analytics(user: dict = Depends(get_current_user)):
    """Analytics for the currently authenticated user."""
    try:
        return get_user_analytics(user["sub"])
    except Exception as exc:
        log.error("Failed to fetch user analytics (user=%s): %s", user.get("sub"), exc, exc_info=True)
        raise HTTPException(500, "Failed to retrieve analytics")
