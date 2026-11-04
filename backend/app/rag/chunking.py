"""Token-approximate text chunking with overlap (word-based; ~tokens for the slice)."""
from __future__ import annotations


def chunk_text(text: str, *, chunk_tokens: int = 512, overlap_ratio: float = 0.1) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunk_tokens = max(1, chunk_tokens)
    step = max(1, int(chunk_tokens * (1 - overlap_ratio)))
    chunks: list[str] = []
    i = 0
    while i < len(words):
        chunks.append(" ".join(words[i : i + chunk_tokens]))
        if i + chunk_tokens >= len(words):
            break
        i += step
    return chunks
