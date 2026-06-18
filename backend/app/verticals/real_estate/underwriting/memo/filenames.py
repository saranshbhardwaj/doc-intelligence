"""Filename helpers for generated IC memo artifacts."""
from __future__ import annotations

import re
from typing import Any


_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._ -]+")
_WHITESPACE_RE = re.compile(r"\s+")


def safe_filename_part(value: Any, *, fallback: str = "IC_Memo", max_length: int = 90) -> str:
    """Return a filesystem/object-key friendly name segment.

    Keeps the human-readable deal name while stripping path separators and other
    characters that produce awkward downloads across browsers and object stores.
    """
    raw = str(value or "").strip()
    cleaned = _FILENAME_SAFE_RE.sub("_", raw)
    cleaned = _WHITESPACE_RE.sub("_", cleaned).strip("._- ")
    if not cleaned:
        cleaned = fallback
    return cleaned[:max_length].strip("._- ") or fallback


def build_memo_filename(deal_name: Any, version: int | None) -> str:
    """Build the friendly DOCX filename shown to analysts on download."""
    deal = safe_filename_part(deal_name, fallback="IC_Memo")
    suffix = f"_v{version}" if version else ""
    return f"{deal}_IC_Memo{suffix}.docx"
