"""Parse uploaded content into plain text for chunking.

Supports text/markdown, CSV, HTML, and URL fetch now. PDF/XLSX are a documented follow-on
(unstructured.io / pdfminer) — see docs/ROADMAP.md. URL fetch is SSRF-guarded: the host is resolved
ONCE, every returned address validated, then the connection is PINNED to a validated IP (the request
is sent to the IP with the original Host header / TLS SNI), so a low-TTL attacker can't rebind the
name to a private address between the check and the fetch. The response body is size-capped.
"""
from __future__ import annotations

import csv
import io
import ipaddress
import re
import socket
from urllib.parse import urlparse

from app.config import Settings, get_settings

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]*\n[ \t]*")
_ALLOWED_PORTS = {80, 443}


def _is_public(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def resolve_safe_target(url: str) -> tuple[str, str, int]:
    """Validate a URL for SSRF and return (host, pinned_public_ip, port). Resolves once and requires
    EVERY resolved address to be public, then returns one to pin the connection to."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("only http(s) URLs are allowed")
    host = parsed.hostname
    if not host:
        raise ValueError("invalid URL host")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in _ALLOWED_PORTS:
        raise ValueError(f"refusing to fetch port {port}; allowed: {sorted(_ALLOWED_PORTS)}")
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"cannot resolve host: {exc}") from exc
    ips = [info[4][0] for info in infos]
    if not ips:
        raise ValueError("host did not resolve")
    for ip in ips:
        if not _is_public(ip):
            raise ValueError("refusing to fetch a private/internal address")
    return host, ips[0], port


def assert_safe_url(url: str) -> None:
    """Back-compat: raise if the URL is unsafe (delegates to resolve_safe_target)."""
    resolve_safe_target(url)


def _strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = _TAG.sub(" ", text)
    return _WS.sub("\n", re.sub(r"[ \t]{2,}", " ", text)).strip()


def _csv_to_text(content: str) -> str:
    rows = list(csv.reader(io.StringIO(content)))
    if not rows:
        return ""
    header = rows[0]
    return "\n".join("; ".join(f"{h}: {v}" for h, v in zip(header, row)) for row in rows[1:])


async def _fetch_url(url: str, *, max_bytes: int) -> str:
    """Fetch a URL with the connection PINNED to a validated public IP (defeats DNS rebinding),
    redirects off, and a hard body-size cap."""
    import httpx

    host, ip, port = resolve_safe_target(url)
    parsed = urlparse(url)
    # Send the request to the pinned IP, preserving the original Host header and (for TLS) SNI so
    # certificate verification still targets the real hostname.
    host_part = f"[{ip}]" if ":" in ip else ip  # bracket IPv6 literals so the pinned netloc stays valid
    pinned = parsed._replace(netloc=f"{host_part}:{port}").geturl()
    headers = {"Host": host}
    extensions = {"sni_hostname": host} if parsed.scheme == "https" else {}
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        async with client.stream("GET", pinned, headers=headers, extensions=extensions) as resp:
            resp.raise_for_status()
            total = 0
            buf = bytearray()
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("refusing to fetch: response exceeds the size cap")
                buf += chunk
    return _strip_html(buf.decode("utf-8", "replace"))


async def parse_content(
    source_type: str, source_ref: str, content: str | None, settings: Settings | None = None
) -> str:
    st = source_type.lower()
    if st == "url":
        settings = settings or get_settings()
        return await _fetch_url(source_ref, max_bytes=settings.url_fetch_max_bytes)
    if content is None:
        return ""
    if st in ("html", "htm"):
        return _strip_html(content)
    if st == "csv":
        return _csv_to_text(content)
    return content  # text / markdown / plain
