"""Shared LLM and vector-store factories (LM Studio for LLM, Ollama for embeddings)."""

import os
import logging
import shutil
import subprocess
import httpx
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from app.config import LM_STUDIO_BASE_URL, LLM_MODEL

log = logging.getLogger(__name__)
_active_model = LLM_MODEL
_llm_cache: dict = {}


def list_available_models() -> list[dict]:
    """Fetch all models available in LM Studio."""
    base = LM_STUDIO_BASE_URL.rstrip("/")
    try:
        resp = httpx.get(f"{base}/models", timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except httpx.ConnectError:
        log.error("Cannot reach LM Studio at %s", base)
        return []
    except Exception as e:
        log.warning("Failed to list models: %s", e)
        return []


def get_active_model() -> str:
    """Return the currently selected model id."""
    return _active_model


def set_active_model(model_id: str) -> None:
    """Switch the active LLM model at runtime."""
    global _active_model, _llm_cache
    _active_model = model_id
    _llm_cache.clear()
    log.info("Active model switched to '%s'", model_id)


def is_no_model_error(e: Exception) -> bool:
    """Return True when the exception is LM Studio's 'No models loaded' error."""
    return "No models loaded" in str(e)


def ensure_model_loaded() -> bool:
    """Check LM Studio and load the configured model if it isn't already loaded.

    Returns True if the model is ready, False otherwise.
    """
    # LM_STUDIO_BASE_URL already ends with /v1
    base = LM_STUDIO_BASE_URL.rstrip("/")

    # 1. Check if LM Studio is reachable and model is already loaded
    try:
        resp = httpx.get(f"{base}/models", timeout=10)
        resp.raise_for_status()
        models = resp.json().get("data", [])
        loaded_ids = [m.get("id", "") for m in models]
        log.info("LM Studio models currently loaded: %s", loaded_ids)

        if any(_active_model in mid for mid in loaded_ids):
            log.info("Model '%s' is already loaded.", _active_model)
            return True
    except httpx.ConnectError:
        log.error("Cannot reach LM Studio at %s — is it running?", base)
        return False
    except Exception as e:
        log.warning("Failed to list models: %s", e)

    # 2. Try to load the model via LM Studio's API
    log.info("Requesting LM Studio to load model '%s'...", _active_model)
    try:
        load_resp = httpx.post(
            f"{base}/models/load",
            json={"model": _active_model},
            timeout=300,  # model loading can take a while
        )
        if load_resp.status_code < 400:
            log.info("Model '%s' loaded successfully.", _active_model)
            return True
        else:
            log.warning(
                "LM Studio returned %s when loading model: %s",
                load_resp.status_code,
                load_resp.text[:300],
            )
    except Exception as e:
        log.warning("Could not auto-load model via API: %s", e)

    # 2.5. Try loading via the LM Studio CLI ('lms load <model>')
    log.info("Trying 'lms load %s' CLI fallback...", _active_model)
    try:
        result = subprocess.run(
            ["lms", "load", _active_model],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            log.info("'lms load' succeeded for model '%s'.", _active_model)
            return True
        log.warning("'lms load' returned code %d: %s", result.returncode, result.stderr[:200])
    except FileNotFoundError:
        log.debug("'lms' CLI not found in PATH; skipping.")
    except Exception as e:
        log.warning("'lms load' failed: %s", e)

    # 3. Fallback — send a tiny warm-up request so LM Studio auto-loads on demand
    log.info("Falling back to warm-up request so LM Studio loads model on demand...")
    try:
        warmup = httpx.post(
            f"{base}/chat/completions",
            json={
                "model": _active_model,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
            },
            timeout=300,
        )
        if warmup.status_code < 400:
            log.info("Warm-up succeeded — model '%s' is ready.", LLM_MODEL)
            return True
        log.warning("Warm-up returned %s: %s", warmup.status_code, warmup.text[:300])
    except Exception as e:
        log.error("Warm-up request failed: %s", e)

    return False



def get_llm(temperature: float = 0.3, num_predict: int = 1024):
    """Return a cached LM Studio-backed LLM that outputs strings."""
    key = (_active_model, temperature, num_predict, False)
    if key not in _llm_cache:
        _llm_cache[key] = ChatOpenAI(
            model=_active_model,
            base_url=LM_STUDIO_BASE_URL,
            api_key="lm-studio",
            temperature=temperature,
            max_tokens=num_predict,
        ) | StrOutputParser()
    return _llm_cache[key]


def get_llm_streaming(temperature: float = 0.3, num_predict: int = 1024):
    """Return a cached LM Studio-backed streaming LLM that outputs string tokens."""
    key = (_active_model, temperature, num_predict, True)
    if key not in _llm_cache:
        _llm_cache[key] = ChatOpenAI(
            model=_active_model,
            base_url=LM_STUDIO_BASE_URL,
            api_key="lm-studio",
            temperature=temperature,
            max_tokens=num_predict,
            streaming=True,
        ) | StrOutputParser()
    return _llm_cache[key]

