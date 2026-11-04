"""Unit tests for the deterministic hashing embedding provider (offline retrieval substrate)."""
from __future__ import annotations

import math

from app.rag.embeddings import HashingEmbeddingProvider


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class TestHashingEmbeddingProvider:
    async def test_dim_and_determinism(self) -> None:
        provider = HashingEmbeddingProvider(dim=256)
        first = (await provider.embed(["overtime hours technician"]))[0]
        second = (await provider.embed(["overtime hours technician"]))[0]
        assert len(first) == 256
        assert first == second

    async def test_unit_normalized(self) -> None:
        provider = HashingEmbeddingProvider(dim=128)
        vec = (await provider.embed(["alpha beta gamma"]))[0]
        assert abs(math.sqrt(sum(x * x for x in vec)) - 1.0) < 1e-9

    async def test_related_more_similar_than_unrelated(self) -> None:
        provider = HashingEmbeddingProvider(dim=512)
        base, related, unrelated = await provider.embed(
            [
                "technician overtime schedule hours",
                "overtime hours for the technician",
                "refrigerant vendor pricing catalog",
            ]
        )
        assert _cosine(base, related) > _cosine(base, unrelated)
