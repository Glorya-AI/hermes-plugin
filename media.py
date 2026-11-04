"""Download finished Glorya files into the plugin's data dir so Hermes can attach them to a chat.

Hermes attaches only local files (``MEDIA:/abs/path``). Downloads are https-only, size-capped and
written atomically; a file that is too big or fails stays a link.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse

_EXTENSIONS = {
    "video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm",
    "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif",
}
_ALLOWED_SUFFIXES = frozenset(_EXTENSIONS.values()) | {".jpeg"}
_SAFE = re.compile(r"[^A-Za-z0-9_-]+")
_CHUNK = 1 << 16
USER_AGENT = "glorya-hermes-plugin/0.1 (+https://github.com/Glorya-AI/hermes-plugin)"


class TooLarge(Exception):
    pass


def _public_host(host: str) -> bool:
    """True when every address the host resolves to is public (no loopback, private or link-local)."""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            return False
    return bool(infos)


def _suffix(url: str, content_type: str) -> Optional[str]:
    by_type = _EXTENSIONS.get(content_type.split(";")[0].strip().lower())
    if by_type:
        return by_type
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in _ALLOWED_SUFFIXES else None


def _open(url: str, timeout: float):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - https enforced by caller


def download(url: str, folder: Path, name: str, max_bytes: int, *, timeout: float = 60,
              opener: Callable[[str, float], Any] = _open, host_check: Callable[[str], bool] = _public_host) -> Path:
    """Fetch ``url`` into ``folder/<name><ext>`` and return the path. Raises on any refusal."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("only plain https links are downloaded")
    if not host_check(parsed.hostname):
        raise ValueError("refusing a non-public host")
    folder.mkdir(parents=True, exist_ok=True)
    with opener(url, timeout) as response:
        final = urlparse(response.geturl() if hasattr(response, "geturl") else url)
        if final.scheme != "https":
            raise ValueError("redirected away from https")
        length = response.headers.get("Content-Length")
        if length and length.isdigit() and int(length) > max_bytes:
            raise TooLarge(f"{int(length)} bytes")
        suffix = _suffix(url, response.headers.get("Content-Type", ""))
        if suffix is None:
            raise ValueError("not an image or video")
        target = folder / f"{_SAFE.sub('-', name)[:80] or 'file'}{suffix}"
        handle, temp_name = tempfile.mkstemp(dir=folder, prefix=".part-")
        written = 0
        try:
            with os.fdopen(handle, "wb") as out:
                while chunk := response.read(_CHUNK):
                    written += len(chunk)
                    if written > max_bytes:
                        raise TooLarge(f"over {max_bytes} bytes")
                    out.write(chunk)
            if written == 0:
                raise ValueError("empty file")
            os.replace(temp_name, target)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise
    return target


def fetch_assets(assets: list[dict[str, Any]], folder: Path, max_bytes: int, limit: int = 4,
                 **kwargs: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Download up to ``limit`` assets (videos first). Returns ``(files, links)``: what was saved and
    what stays a link (too big, unreadable or over the limit)."""
    ordered = sorted(assets, key=lambda a: 0 if a.get("type") == "video" else 1)
    files: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    for index, asset in enumerate(ordered):
        url = str(asset.get("url") or "")
        if len(files) >= limit or not url:
            links.append(asset)
            continue
        name = str(asset.get("id") or f"asset-{index + 1}")
        try:
            path = download(url, folder, name, max_bytes, **kwargs)
        except Exception:
            links.append(asset)
            continue
        files.append({"path": str(path), "asset_id": asset.get("id"), "type": asset.get("type"),
                      "label": asset.get("label"), "url": url, "poster_url": asset.get("poster_url")})
    return files, links
