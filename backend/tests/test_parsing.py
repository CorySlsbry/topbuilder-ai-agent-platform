"""Tests for RAG parsing + the SSRF guard on URL ingestion."""
from __future__ import annotations

import pytest

from app.rag.parsing import _csv_to_text, _strip_html, assert_safe_url, parse_content


class TestSsrfGuard:
    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost/x",
            "http://127.0.0.1/",
            "http://169.254.169.254/latest/meta-data",  # cloud metadata
            "http://10.0.0.5/internal",
            "http://[::1]/",
            "ftp://example.com/file",
        ],
    )
    def test_blocks_unsafe(self, url: str) -> None:
        with pytest.raises(ValueError):
            assert_safe_url(url)

    def test_allows_public_ip(self) -> None:
        assert_safe_url("http://1.1.1.1/")  # public, no DNS needed for an IP literal


class TestParsers:
    def test_strip_html_drops_tags_and_scripts(self) -> None:
        out = _strip_html("<div><script>evil()</script><p>hello <b>world</b></p></div>")
        assert "hello" in out and "world" in out and "evil" not in out

    def test_csv_to_text(self) -> None:
        out = _csv_to_text("name,role\nAlice,admin\nBob,viewer")
        assert "name: Alice; role: admin" in out
        assert "name: Bob; role: viewer" in out

    async def test_parse_text_passthrough(self) -> None:
        assert await parse_content("text", "notes.txt", "just text") == "just text"

    async def test_parse_url_blocks_localhost(self) -> None:
        with pytest.raises(ValueError):
            await parse_content("url", "http://127.0.0.1/secret", None)
