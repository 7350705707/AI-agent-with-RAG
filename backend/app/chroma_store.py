"""ChromaDB vector store for knowledge base semantic search.

Embedding strategy (controlled by EMBEDDING_MODE env var):
  "auto"     — LM Studio /v1/embeddings first; falls back to ChromaDB ONNX
               (all-MiniLM-L6-v2) when LM Studio is unreachable.  Fully offline.
  "lmstudio" — LM Studio only.  Raises RuntimeError at startup if unreachable.
               Re-index all documents after switching to ensure a consistent
               vector space (use POST /api/admin/reindex).

Hybrid search: combines ChromaDB cosine-similarity (vector) with BM25-style
keyword ranking, then fuses results via Reciprocal Rank Fusion (RRF) so that
rare keywords that happen to be semantically distant still surface.
"""

import logging
import math
import re
from collections import defaultdict
from typing import List, Optional

import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings

from app.config import CHROMA_DIR, CHROMA_COLLECTION_NAME, EMBEDDING_MODE, EMBEDDING_BATCH_SIZE, EMBEDDING_TIMEOUT, LM_STUDIO_BASE_URL

log = logging.getLogger(__name__)

COLLECTION_NAME = CHROMA_COLLECTION_NAME

# ── Singleton client / collection ──────────────────────────────────────────
_client: Optional[chromadb.Client] = None
_collection: Optional[chromadb.Collection] = None


# ── Embedding function ─────────────────────────────────────────────────────

class LMStudioEmbeddingFunction(EmbeddingFunction):
    """Call LM Studio's OpenAI-compatible /v1/embeddings endpoint.

    Uses a short timeout for the startup probe and a longer configurable
    timeout for real embedding calls (EMBEDDING_TIMEOUT env var, default 120 s).
    """

    def __init__(self, base_url: str, probe: bool = False):
        import httpx
        self._url = base_url.rstrip("/") + "/embeddings"
        # Probe needs to fail fast; real calls need time for large batches.
        timeout = 3 if probe else EMBEDDING_TIMEOUT
        self._http = httpx.Client(timeout=timeout)

    def __call__(self, input: Documents) -> Embeddings:  # noqa: A002
        resp = self._http.post(
            self._url,
            json={"input": input},
            headers={"Authorization": "Bearer lm-studio"},
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return [item["embedding"] for item in data]


def _make_embedding_function() -> EmbeddingFunction | None:
    """Build embedding function according to EMBEDDING_MODE.

    "lmstudio": LM Studio only — raises RuntimeError if /v1/embeddings unreachable.
    "auto"    : LM Studio first; falls back to ChromaDB ONNX all-MiniLM-L6-v2.
    """
    try:
        probe_ef = LMStudioEmbeddingFunction(LM_STUDIO_BASE_URL, probe=True)
        probe_ef(["test"])  # quick probe with short timeout
        ef = LMStudioEmbeddingFunction(LM_STUDIO_BASE_URL, probe=False)  # long-timeout client for real calls
        log.info("ChromaDB: using LM Studio embedding endpoint (%s)", LM_STUDIO_BASE_URL)
        return ef
    except Exception as exc:
        if EMBEDDING_MODE == "lmstudio":
            raise RuntimeError(
                f"EMBEDDING_MODE=lmstudio but LM Studio /v1/embeddings is not reachable "
                f"({LM_STUDIO_BASE_URL}). Start an embedding model in LM Studio or set "
                f"EMBEDDING_MODE=auto to allow the ONNX fallback."
            ) from exc
        log.info("LM Studio embedding not available (%s); using default ONNX embedding.", exc)
        try:
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
            return DefaultEmbeddingFunction()
        except Exception as exc2:
            log.warning("Default embedding function unavailable (%s); ChromaDB will use its internal default.", exc2)
            return None


def check_embedding_health() -> dict:
    """Probe LM Studio /v1/embeddings and return a status dict.

    Returns keys: lmstudio_available, lmstudio_url, mode, error (on failure).
    """
    try:
        ef = LMStudioEmbeddingFunction(LM_STUDIO_BASE_URL, probe=True)
        ef(["health-check"])
        return {
            "lmstudio_available": True,
            "lmstudio_url": LM_STUDIO_BASE_URL,
            "mode": EMBEDDING_MODE,
            "active_backend": "lmstudio",
        }
    except Exception as exc:
        active = "unavailable" if EMBEDDING_MODE == "lmstudio" else "onnx_fallback"
        return {
            "lmstudio_available": False,
            "lmstudio_url": LM_STUDIO_BASE_URL,
            "mode": EMBEDDING_MODE,
            "active_backend": active,
            "error": str(exc),
        }


def _get_collection() -> chromadb.Collection:
    global _client, _collection
    if _collection is not None:
        return _collection

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    ef = _make_embedding_function()
    kwargs: dict = {"name": COLLECTION_NAME, "metadata": {"hnsw:space": "cosine"}}
    if ef is not None:
        kwargs["embedding_function"] = ef

    _collection = _client.get_or_create_collection(**kwargs)
    log.info("ChromaDB collection '%s' ready (%d chunks).", COLLECTION_NAME, _collection.count())
    return _collection


def reset_collection() -> None:
    """Clear the cached ChromaDB client/collection singleton.

    The next call to _get_collection() will re-initialize both the client and
    the collection using the embedding function that is currently available
    (e.g. LM Studio after the embedding model has been auto-loaded).
    """
    global _client, _collection
    _collection = None
    _client = None
    log.info("ChromaDB collection cache cleared — will re-initialize on next access.")


# ── Public API (matches the old SQLite knowledge functions) ────────────────

def add_knowledge_chunks(doc_id: str, filename: str, chunks: List[dict]) -> int:
    """Store document chunks in ChromaDB with semantic embeddings.

    Args:
        doc_id:   UUID of the parent knowledge document.
        filename: Display name of the document (stored in metadata for search results).
        chunks:   List of {'content': str, 'metadata': str | dict} dicts.

    Returns:
        Number of chunks stored.
    """
    if not chunks:
        return 0

    collection = _get_collection()
    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[dict] = []

    for i, chunk in enumerate(chunks):
        ids.append(f"{doc_id}_{i}")
        documents.append(chunk["content"])
        # chunk["metadata"] may be a dict (from enriched loader) or a str repr
        raw_meta = chunk.get("metadata", {})
        if isinstance(raw_meta, str):
            # Legacy string repr — store as-is
            meta = {"doc_id": doc_id, "filename": filename, "chunk_meta": raw_meta, "chunk_index": i}
        else:
            meta = {"doc_id": doc_id, "filename": filename, **{k: str(v) for k, v in raw_meta.items()}}
        metadatas.append(meta)

    # upsert in batches — avoids HTTP timeout when embedding hundreds of chunks
    total_upserted = 0
    for start in range(0, len(ids), EMBEDDING_BATCH_SIZE):
        end = start + EMBEDDING_BATCH_SIZE
        collection.upsert(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )
        total_upserted += len(ids[start:end])
        log.debug(
            "ChromaDB: upserted batch %d-%d / %d for doc_id=%s",
            start + 1, min(end, len(ids)), len(ids), doc_id,
        )
    log.info("ChromaDB: upserted %d chunks for doc_id=%s (%s)", total_upserted, doc_id, filename)
    return total_upserted


# ── BM25-style keyword scorer ──────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _bm25_score(query_tokens: List[str], doc_tokens: List[str], avg_dl: float, k1: float = 1.5, b: float = 0.75) -> float:
    """Compute BM25 score for a single document against the query tokens."""
    freq: dict = defaultdict(int)
    for t in doc_tokens:
        freq[t] += 1
    dl = len(doc_tokens)
    score = 0.0
    for token in set(query_tokens):
        tf = freq.get(token, 0)
        if tf == 0:
            continue
        idf = math.log(1 + 1)  # simplified IDF = 1 (single-shard, no N/df)
        tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / max(avg_dl, 1)))
        score += idf * tf_norm
    return score


def _reciprocal_rank_fusion(ranked_lists: List[List[str]], k: int = 60) -> List[str]:
    """Fuse multiple ranked ID lists via RRF. Returns IDs sorted by fused score."""
    scores: dict = defaultdict(float)
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, 1):
            scores[doc_id] += 1.0 / (k + rank)
    return sorted(scores.keys(), key=lambda x: scores[x], reverse=True)


def search_knowledge(query: str, limit: int = 10, extra_keywords: List[str] | None = None) -> List[dict]:
    """Hybrid (vector + BM25) search over all knowledge chunks.

    Returns list of dicts: {'content', 'doc_id', 'filename', 'score', 'metadata'}

    Args:
        query:          User question / refined search query.
        limit:          Number of final results to return.
        extra_keywords: Additional keywords (e.g. from LLM expansion) to boost BM25.
    """
    collection = _get_collection()
    total = collection.count()
    if total == 0:
        return []

    # ── Vector search (semantic) ───────────────────────────────────────────
    vector_limit = min(limit * 4, total)  # fetch more candidates for re-ranking
    try:
        vec_results = collection.query(
            query_texts=[query],
            n_results=vector_limit,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        log.warning("ChromaDB vector query failed: %s", exc)
        vec_results = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    ids_list = vec_results.get("ids", [[]])
    if not ids_list or not ids_list[0]:
        return []

    # Build lookup: chunk_id -> {content, meta, vector_score}
    chunk_map: dict = {}
    for chunk_id, doc, meta, dist in zip(
        ids_list[0],
        vec_results["documents"][0],
        vec_results["metadatas"][0],
        vec_results["distances"][0],
    ):
        chunk_map[chunk_id] = {
            "content": doc,
            "meta": meta,
            "vector_score": round(1.0 - dist, 4),
        }

    # ── BM25 keyword search over fetched candidates ────────────────────────
    combined_query = query
    if extra_keywords:
        combined_query = query + " " + " ".join(extra_keywords)
    query_tokens = _tokenize(combined_query)

    all_doc_tokens = {cid: _tokenize(info["content"]) for cid, info in chunk_map.items()}
    avg_dl = sum(len(t) for t in all_doc_tokens.values()) / max(len(all_doc_tokens), 1)

    bm25_scored = sorted(
        chunk_map.keys(),
        key=lambda cid: _bm25_score(query_tokens, all_doc_tokens[cid], avg_dl),
        reverse=True,
    )
    vector_ranked = list(chunk_map.keys())  # already sorted by vector distance

    # ── Reciprocal Rank Fusion ─────────────────────────────────────────────
    fused = _reciprocal_rank_fusion([vector_ranked, bm25_scored])

    output: List[dict] = []
    seen_docs: dict = {}  # doc_id -> count, to diversify across documents
    for chunk_id in fused[:limit * 2]:
        info = chunk_map[chunk_id]
        meta = info["meta"]
        doc_id = meta.get("doc_id", "")
        seen_docs[doc_id] = seen_docs.get(doc_id, 0) + 1
        # Allow at most 3 chunks per source doc (diversity)
        if seen_docs[doc_id] > 3:
            continue
        output.append({
            "content": info["content"],
            "doc_id": doc_id,
            "filename": meta.get("filename", "unknown"),
            "score": info["vector_score"],
            "metadata": meta,
        })
        if len(output) >= limit:
            break

    log.debug("Hybrid search '%s': returned %d chunks", query[:60], len(output))
    return output


def delete_knowledge_chunks(doc_id: str) -> None:
    """Remove all chunks belonging to a document from ChromaDB."""
    try:
        _get_collection().delete(where={"doc_id": doc_id})
        log.info("ChromaDB: deleted chunks for doc_id=%s", doc_id)
    except Exception as exc:
        log.warning("ChromaDB delete failed for doc_id=%s: %s", doc_id, exc)


def clear_knowledge() -> None:
    """Drop and recreate the collection (removes all chunks)."""
    global _client, _collection
    if _client is None:
        _get_collection()  # ensure client is created
    if _client is not None:
        try:
            _client.delete_collection(COLLECTION_NAME)
            log.info("ChromaDB: collection '%s' deleted.", COLLECTION_NAME)
        except Exception as exc:
            log.warning("ChromaDB clear failed: %s", exc)
    _collection = None  # force re-creation on next access


def get_knowledge_chunk_count() -> int:
    """Return total number of chunks stored in ChromaDB."""
    try:
        return _get_collection().count()
    except Exception:
        return 0
