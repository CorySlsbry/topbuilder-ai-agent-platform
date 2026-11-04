"""Unit tests for RAG text chunking."""
from __future__ import annotations

from app.rag.chunking import chunk_text


class TestChunkText:
    def test_empty(self) -> None:
        assert chunk_text("") == []

    def test_short_text_single_chunk(self) -> None:
        assert chunk_text("alpha beta gamma", chunk_tokens=10) == ["alpha beta gamma"]

    def test_splits_with_overlap(self) -> None:
        words = " ".join(str(i) for i in range(25))
        chunks = chunk_text(words, chunk_tokens=10, overlap_ratio=0.2)  # step = 8
        assert len(chunks) == 3
        assert chunks[0].split()[0] == "0" and chunks[0].split()[-1] == "9"
        assert chunks[1].split()[0] == "8"  # overlap with the previous chunk's tail

    def test_covers_all_words(self) -> None:
        words = " ".join(str(i) for i in range(100))
        seen: set[str] = set()
        for chunk in chunk_text(words, chunk_tokens=30, overlap_ratio=0.1):
            seen.update(chunk.split())
        assert seen == {str(i) for i in range(100)}
