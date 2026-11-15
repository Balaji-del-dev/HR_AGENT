"""Embedding providers: Ollama (all-minilm, 384 dimensions) or a deterministic hash embedder."""

import hashlib
import math
import re
from functools import lru_cache
from itertools import pairwise
from typing import Protocol

from django.conf import settings


class Embedder(Protocol):
    model_name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class HashEmbedder:
    """Feature hashing over lowercase word unigrams and bigrams. Offline and repeatable.

    Good enough to rank chunks that share terms with a query; no semantics.
    """

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions
        self.model_name = f"hash-{dimensions}"

    def _vector(self, text: str) -> list[float]:
        words = re.findall(r"[a-z0-9+#.]+", text.lower())
        features = words + [f"{a} {b}" for a, b in pairwise(words)]
        vector = [0.0] * self.dimensions
        for feature in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimensions
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class OllamaEmbedder:
    def __init__(self, model: str, base_url: str) -> None:
        from langchain_ollama import OllamaEmbeddings

        self.model_name = f"ollama:{model}"
        self._client = OllamaEmbeddings(model=model, base_url=base_url)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._client.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed_query(text)


@lru_cache(maxsize=2)
def get_embedder() -> Embedder:
    if settings.EMBEDDING_PROVIDER == "ollama":
        return OllamaEmbedder(settings.EMBEDDING_MODEL, settings.OLLAMA_BASE_URL)
    if settings.EMBEDDING_PROVIDER == "hash":
        return HashEmbedder(settings.EMBEDDING_DIMENSIONS)
    raise ValueError(f"Unknown embedding provider {settings.EMBEDDING_PROVIDER!r}")


def embed_query_safely(text: str) -> list[float] | None:
    """Query embedding, or None when the embedding service is down (search falls back to lexical)."""
    try:
        return get_embedder().embed_query(text)
    except Exception:  # noqa: BLE001
        return None
