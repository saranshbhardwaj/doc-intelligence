#!/usr/bin/env python3
"""Feed existing extracted text file into LLM for structured extraction.

Usage:
  python backend/scripts/llm_from_text.py <raw_text_file> [--max-input-chars N] [--no-save]

Smart truncation (if text length > max-input-chars):
  - Keep first 80% of allowed characters
  - Keep last 20% of allowed characters
  - Insert marker in the middle

Outputs (unless --no-save):
  logs/raw_llm_response/<timestamp>_<stem>_llm.json          Raw LLM structured response
  logs/parsed/<timestamp>_<stem>_normalized.json             Normalized output with red flags
  logs/parsed/<timestamp>_<stem>_llm.meta.json               Metadata summary
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))
load_dotenv(backend_root / ".env")

from app.config import settings
from app.services.llm_client import LLMClient
from app.utils.normalization import _normalize_llm_output
from app.services.risk_detector import detect_red_flags
from app.models import ExtractedData
from app.utils.logging import logger


def _ts():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def smart_truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    keep_start = int(limit * 0.8)
    keep_end = limit - keep_start
    return (
        text[:keep_start]
        + f"\n\n... [SMART TRUNCATED: removed {len(text) - limit:,} chars from middle section] ...\n\n"
        + text[-keep_end:]
    )


def run_llm(raw_text_path: Path, max_input_chars: int, save: bool):
    if not raw_text_path.exists():
        raise FileNotFoundError(f"Raw text file not found: {raw_text_path}")

    text = raw_text_path.read_text()
    original_len = len(text)
    truncated_text = smart_truncate(text, max_input_chars)

    timestamp = _ts()
    stem = raw_text_path.stem.replace("_raw_docai", "")

    llm = LLMClient(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        max_input_chars=settings.llm_max_input_chars,
        timeout_seconds=settings.llm_timeout_seconds,
    )

    start = time.time()
    response = llm.extract_structured_data(truncated_text)
    llm_secs = time.time() - start

    # Normalize
    try:
        normalized = _normalize_llm_output(response)
    except Exception as e:
        logger.exception(f"Normalization failed: {e}")
        normalized = response

    # Red flags
    try:
        extracted_obj = ExtractedData(**normalized.get("data", {}))
        red_flags = detect_red_flags(extracted_obj)
        normalized.setdefault("data", {})["red_flags"] = red_flags
    except Exception as e:
        logger.warning(f"Red flag detection failed: {e}")
        normalized.setdefault("data", {})["red_flags"] = []

    if save:
        raw_llm_path = settings.raw_llm_dir / f"{timestamp}_{stem}_llm.json"
        save_json(raw_llm_path, response)
        norm_path = settings.parsed_dir / f"{timestamp}_{stem}_normalized.json"
        save_json(norm_path, normalized)
        meta_path = settings.parsed_dir / f"{timestamp}_{stem}_llm.meta.json"
        meta = {
            "raw_text_file": str(raw_text_path),
            "timestamp": timestamp,
            "original_chars": original_len,
            "used_chars": len(truncated_text),
            "truncated": original_len > max_input_chars,
            "llm_seconds": round(llm_secs, 2),
            "red_flags": len(normalized.get("data", {}).get("red_flags", [])),
        }
        save_json(meta_path, meta)

    print(json.dumps({
        "original_chars": original_len,
        "used_chars": len(truncated_text),
        "truncated": original_len > max_input_chars,
        "llm_seconds": llm_secs,
        "red_flag_count": len(normalized.get("data", {}).get("red_flags", []))
    }, indent=2))


def main():
    ap = argparse.ArgumentParser(description="Run LLM on previously extracted raw text")
    ap.add_argument("raw_text_file", type=str, help="Path to raw extracted text file")
    ap.add_argument("--max-input-chars", type=int, default=130000, help="Character limit before smart truncation")
    ap.add_argument("--no-save", action="store_true", help="Do not write output artifacts")
    args = ap.parse_args()

    try:
        run_llm(Path(args.raw_text_file), args.max_input_chars, save=not args.no_save)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
