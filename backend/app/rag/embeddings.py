"""Embedding providers behind one interface.

- HashingEmbeddingProvider: deterministic, offline, dependency-free (feature hashing + L2 norm).
  Captures lexical overlap so retrieval works in tests/CI with no API key.
- OpenAIEmbeddingProvider: real `text-embedding-3-large`, used when EMBEDDING_PROVIDER=openai + key.
"""
from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable

from app.config import Settings, get_settings


@runtime_checkable
class EmbeddingProvider(Protocol):
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbeddingProvider:
    def __init__(self, dim: int) -> None:
        self.dim = dim

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in text.lower().split():
            # Non-cryptographic: feature-hashing a token into the embedding space, not a security control.
            h = int(hashlib.md5(token.encode(), usedforsecurity=False).hexdigest(), 16)
            vec[h % self.dim] += 1.0 if (h >> 8) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str, model: str, dim: int) -> None:
        self.api_key = api_key
        self.model = model
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        resp = await client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    settings = settings or get_settings()
    if settings.embedding_provider.lower() == "openai" and settings.openai_api_key:
        return OpenAIEmbeddingProvider(
            settings.openai_api_key, settings.embedding_model, settings.embedding_dim
        )
    return HashingEmbeddingProvider(settings.embedding_dim)
