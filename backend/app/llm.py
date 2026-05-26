"""Shared LLM and vector-store factories (LM Studio or vLLM for LLM, LM Studio for embeddings)."""

import os
import logging
import shutil
import subprocess
import httpx
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from app.config import (
    LM_STUDIO_BASE_URL, LLM_MODEL, MODEL_CONTEXT_LENGTH,
    LLM_BACKEND, VLLM_BASE_URL, VLLM_API_KEY, EMBEDDING_MODEL,
)

log = logging.getLogger(__name__)
_active_model = LLM_MODEL
_llm_cache: dict = {}


def _llm_base_url() -> str:
    """Return the active LLM backend base URL."""
    return VLLM_BASE_URL if LLM_BACKEND == "vllm" else LM_STUDIO_BASE_URL


def _llm_api_key() -> str:
    """Return the API key for the active LLM backend."""
    return VLLM_API_KEY if LLM_BACKEND == "vllm" else "lm-studio"


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


def is_context_size_error(e: Exception) -> bool:
    """Return True when the exception indicates the prompt exceeded the model's context window."""
    msg = str(e).lower()
    return any(
        phrase in msg
        for phrase in (
            "context size",
            "context length",
            "context window",
            "max_tokens",
            "token limit",
            "too many tokens",
            "prompt is too long",
            "exceeds the maximum",
            "n_keep",
            "n_ctx",
        )
    )


def ensure_model_loaded() -> bool:
    """Check the active LLM backend and load the configured model if not already loaded.

    Returns True if the model is ready, False otherwise.
    """
    # For vLLM, models are pre-loaded — just probe the endpoint.
    if LLM_BACKEND == "vllm":
        base = VLLM_BASE_URL.rstrip("/")
        try:
            resp = httpx.get(f"{base}/models", timeout=10, headers={"Authorization": f"Bearer {VLLM_API_KEY}"})
            resp.raise_for_status()
            log.info("vLLM is reachable. Models: %s", [m.get('id') for m in resp.json().get('data', [])])
            return True
        except Exception as e:
            log.error("Cannot reach vLLM at %s: %s", base, e)
            return False

    # ── LM Studio path ────────────────────────────────────────────────────
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
            json={"model": _active_model, "config": {"contextLength": MODEL_CONTEXT_LENGTH}},
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
            encoding='utf-8', errors='replace',
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


def ensure_embedding_model_loaded() -> bool:
    """Attempt to load the configured EMBEDDING_MODEL in LM Studio.

    Tries in order:
      0. Quick probe — the model may already be loaded (e.g. loaded after server start).
      1. POST /models/load — LM Studio REST API (current versions).
      2. 'lms load' CLI — fallback for older LM Studio versions.

    After each load attempt the /v1/embeddings endpoint is probed with retries
    so we wait for the model to finish loading before declaring success.

    Returns True once the embedding endpoint is confirmed reachable.
    """
    import time

    if not EMBEDDING_MODEL:
        log.info("EMBEDDING_MODEL env var not set; skipping embedding model auto-load.")
        return False

    base = LM_STUDIO_BASE_URL.rstrip("/")
    embed_url = f"{base}/embeddings"

    def _probe(timeout: float = 10.0) -> bool:
        """Return True if the LM Studio /v1/embeddings endpoint responds."""
        try:
            resp = httpx.post(
                embed_url,
                json={"input": ["ping"]},
                headers={"Authorization": "Bearer lm-studio"},
                timeout=timeout,
            )
            resp.raise_for_status()
            return True
        except Exception:
            return False

    def _probe_with_retries(attempts: int = 10, delay: float = 3.0) -> bool:
        """Probe up to `attempts` times, waiting `delay` s between each try."""
        for i in range(attempts):
            if _probe(timeout=10.0):
                return True
            if i < attempts - 1:
                log.info(
                    "Embedding probe %d/%d not ready — retrying in %.0fs…",
                    i + 1, attempts, delay,
                )
                time.sleep(delay)
        return False

    # ── Step 0: probe first — might already be loaded ────────────────────
    if _probe(timeout=5.0):
        log.info("Embedding model already available at LM Studio.")
        return True

    # ── Step 1: POST /models/load ─────────────────────────────────────────
    log.info("Requesting LM Studio to load embedding model '%s'...", EMBEDDING_MODEL)
    try:
        load_resp = httpx.post(
            f"{base}/models/load",
            json={"model": EMBEDDING_MODEL},
            timeout=120,
        )
        if load_resp.status_code < 400:
            log.info(
                "POST /models/load accepted (HTTP %s). Probing embedding endpoint…",
                load_resp.status_code,
            )
            if _probe_with_retries(attempts=10, delay=3.0):
                log.info("Embedding model '%s' loaded and ready via API.", EMBEDDING_MODEL)
                return True
            log.warning(
                "Embedding endpoint still unreachable after POST /models/load. "
                "Model may still be loading — will try CLI fallback."
            )
        else:
            log.warning(
                "POST /models/load returned HTTP %s: %s",
                load_resp.status_code, load_resp.text[:300],
            )
    except httpx.ConnectError:
        log.error("Cannot reach LM Studio at %s to load embedding model.", base)
        return False
    except Exception as e:
        log.warning("POST /models/load failed: %s", e)

    # ── Step 2: lms CLI fallback ──────────────────────────────────────────
    log.info("Trying 'lms load %s' CLI fallback for embedding model…", EMBEDDING_MODEL)
    try:
        result = subprocess.run(
            ["lms", "load", EMBEDDING_MODEL],
            capture_output=True, text=True, timeout=120,
            encoding='utf-8', errors='replace',
        )
        if result.returncode == 0:
            log.info("'lms load' succeeded for embedding model '%s'.", EMBEDDING_MODEL)
            if _probe_with_retries(attempts=10, delay=3.0):
                log.info("Embedding model '%s' ready after CLI load.", EMBEDDING_MODEL)
                return True
            log.warning("Embedding endpoint still unreachable after CLI load.")
        else:
            log.warning(
                "'lms load' returned code %d: %s",
                result.returncode, result.stderr[:200],
            )
    except FileNotFoundError:
        log.debug("'lms' CLI not found in PATH; skipping CLI fallback.")
    except Exception as e:
        log.warning("'lms load' CLI failed: %s", e)

    return False



def get_llm(temperature: float = 0.3, num_predict: int = 1024):
    """Return a cached LLM (LM Studio or vLLM) that outputs strings."""
    key = (_active_model, temperature, num_predict, False)
    if key not in _llm_cache:
        _llm_cache[key] = ChatOpenAI(
            model=_active_model,
            base_url=_llm_base_url(),
            api_key=_llm_api_key(),
            temperature=temperature,
            max_tokens=num_predict,
        ) | StrOutputParser()
    return _llm_cache[key]


def get_llm_streaming(temperature: float = 0.3, num_predict: int = 1024):
    """Return a cached streaming LLM (LM Studio or vLLM) that outputs string tokens."""
    key = (_active_model, temperature, num_predict, True)
    if key not in _llm_cache:
        _llm_cache[key] = ChatOpenAI(
            model=_active_model,
            base_url=_llm_base_url(),
            api_key=_llm_api_key(),
            temperature=temperature,
            max_tokens=num_predict,
            streaming=True,
        ) | StrOutputParser()
    return _llm_cache[key]

