"""LLM model management controller — list / select / load routes.

Model  : app.llm  (list_available_models / get_active_model / set_active_model / ensure_model_loaded)
View   : JSON responses with model metadata
"""

from fastapi import APIRouter, HTTPException, status

from app.llm import (
    ensure_model_loaded,
    get_active_model,
    list_available_models,
    set_active_model,
)

router = APIRouter(prefix="/api/models", tags=["models"])


# ── List models ────────────────────────────────────────────────────────────
@router.get("")
def api_list_models():
    """List all models available in LM Studio."""
    models = list_available_models()
    active = get_active_model()
    return {
        "active": active,
        "models": [{"id": m.get("id", ""), "object": m.get("object", "")} for m in models],
    }


# ── Select model (metadata only) ───────────────────────────────────────────
@router.post("/select")
def api_select_model(body: dict):
    """Switch the active LLM model at runtime (does not trigger loading)."""
    model_id = body.get("model")
    if not model_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing 'model' field")
    set_active_model(model_id)
    return {"active": model_id}


# ── Load model (select + ensure loaded) ───────────────────────────────────
@router.post("/load")
def api_load_model(body: dict):
    """Select a model and trigger loading it in LM Studio."""
    model_id = body.get("model")
    if not model_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing 'model' field")
    set_active_model(model_id)
    loaded = ensure_model_loaded()
    return {"active": model_id, "loaded": loaded}
