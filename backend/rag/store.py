"""ChromaDB vector store (embeddings are computed by Ollama's nomic-embed-text)."""

from __future__ import annotations

import threading
from typing import Any

from backend.config import settings
from backend.utils.logging import get_logger

log = get_logger(__name__)


class VectorStoreUnavailable(Exception):
    pass


_collection = None
_lock = threading.Lock()


def get_collection():
    global _collection
    if _collection is not None:
        return _collection
    with _lock:
        if _collection is None:
            try:
                import chromadb
                from chromadb.config import Settings as ChromaSettings

                client = chromadb.HttpClient(
                    host=settings.CHROMA_HOST,
                    port=settings.CHROMA_PORT,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                _collection = client.get_or_create_collection(
                    name=settings.CHROMA_COLLECTION,
                    metadata={"hnsw:space": "cosine"},
                    embedding_function=None,
                )
            except Exception as exc:
                raise VectorStoreUnavailable(f"ChromaDB unavailable: {exc}") from exc
    return _collection


def reset_collection_cache() -> None:
    global _collection
    _collection = None


def upsert(ids: list[str], embeddings: list[list[float]], documents: list[str], metadatas: list[dict[str, Any]]) -> None:
    get_collection().upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)


def delete_doc(doc_key: str) -> None:
    get_collection().delete(where={"doc": doc_key})


def query(embedding: list[float], k: int) -> list[dict[str, Any]]:
    res = get_collection().query(query_embeddings=[embedding], n_results=k, include=["documents", "metadatas", "distances"])
    out = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0], strict=False):
        out.append({"text": doc, "metadata": meta or {}, "score": round(1 - float(dist), 4)})
    return out


def count() -> int:
    try:
        return get_collection().count()
    except Exception:
        reset_collection_cache()
        return -1


def ping() -> bool:
    return count() >= 0
