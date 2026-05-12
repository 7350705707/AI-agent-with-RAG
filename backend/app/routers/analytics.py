"""Analytics controller — usage statistics for admin and per-user views."""

from fastapi import APIRouter, Depends

from app.auth import get_current_user, require_admin
from app.database import get_analytics_summary, get_user_analytics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary")
def api_analytics_summary(_admin: dict = Depends(require_admin)):
    """Platform-wide analytics — admin only."""
    return get_analytics_summary()


@router.get("/me")
def api_my_analytics(user: dict = Depends(get_current_user)):
    """Analytics for the currently authenticated user."""
    return get_user_analytics(user["sub"])
