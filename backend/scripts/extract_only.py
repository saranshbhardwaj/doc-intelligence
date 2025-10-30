#!/usr/bin/env python3
"""Extract raw text from a PDF using configured parser (tier logic or forced parser) without LLM.

Usage:
  python backend/scripts/extract_only.py <pdf_path> [--pdf-type auto|digital|scanned] [--parser auto|pymupdf|google_documentai] [--output-dir <dir>] [--max-chars N]

Behavior:
  - If --pdf-type auto: detect via pdf_utils.detect_pdf_type
  - If --parser auto: use ParserFactory based on tier + pdf_type (respects FORCE_PARSER / FORCE_USER_TIER)
  - Saves raw text and metadata JSON.
  - Optionally limits stored text to --max-chars but reports full length.

Outputs (default dir = logs/raw):
  <output-dir>/<timestamp>_<stem>_raw.txt
  <output-dir>/<timestamp>_<stem>_meta.json
"""
from __future__ import annotations
import argparse
import asyncio
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
from app.services.parsers import ParserFactory
from app.utils.pdf_utils import detect_pdf_type
from app.utils.logging import logger


def _ts():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def save_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


async def extract(pdf_path: Path, pdf_type_opt: str, parser_opt: str, output_dir: Path, max_chars: int | None):
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Determine pdf_type
    if pdf_type_opt == "auto":
        pdf_type = detect_pdf_type(str(pdf_path))
    else:
        pdf_type = pdf_type_opt

    user_tier = settings.force_user_tier if settings.force_user_tier else "free"

    # Determine parser
    if parser_opt == "auto":
        parser = ParserFactory.get_parser(user_tier, pdf_type)
        if not parser:
            raise RuntimeError(f"No parser available for tier={user_tier} pdf_type={pdf_type}")
    else:
        parser = ParserFactory._create_parser(parser_opt)

    logger.info(f"Extracting with parser={parser.name} pdf_type={pdf_type}")
    start = time.time()
    parser_out = await parser.parse(str(pdf_path), pdf_type)
    elapsed = time.time() - start

    raw_text_full = parser_out.text
    stored_text = raw_text_full[:max_chars] if max_chars and len(raw_text_full) > max_chars else raw_text_full

    timestamp = _ts()
    stem = pdf_path.stem

    txt_path = output_dir / f"{timestamp}_{stem}_raw.txt"
    meta_path = output_dir / f"{timestamp}_{stem}_meta.json"

    save_text(txt_path, stored_text)
    meta = {
        "file": str(pdf_path),
        "timestamp": timestamp,
        "parser": parser_out.parser_name,
        "parser_version": parser_out.parser_version,
        "pdf_type": pdf_type,
        "pages": parser_out.page_count,
        "cost_usd": parser_out.cost_usd,
        "processing_ms": parser_out.processing_time_ms,
        "elapsed_s": round(elapsed, 2),
        "raw_chars_full": len(raw_text_full),
        "raw_chars_stored": len(stored_text),
        "truncated": len(stored_text) < len(raw_text_full),
    }
    save_json(meta_path, meta)

    print(json.dumps({"text_file": str(txt_path), "meta_file": str(meta_path), **meta}, indent=2))


def main():
    ap = argparse.ArgumentParser(description="Extract raw text only (no LLM)")
    ap.add_argument("pdf", type=str, help="Path to PDF")
    ap.add_argument("--pdf-type", default="auto", choices=["auto", "digital", "scanned"], help="PDF type override")
    ap.add_argument("--parser", default="auto", choices=["auto", "pymupdf", "google_documentai", "llmwhisperer"], help="Force parser")
    ap.add_argument("--output-dir", type=str, default="logs/raw", help="Directory for output files")
    ap.add_argument("--max-chars", type=int, help="Store only first N chars of extracted text")
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    output_dir = Path(args.output_dir)

    try:
        asyncio.run(extract(pdf_path, args.pdf_type, args.parser, output_dir, args.max_chars))
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
