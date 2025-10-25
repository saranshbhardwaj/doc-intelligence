# app/utils/file_utils.py
from pathlib import Path
from datetime import datetime
from app.config import settings
from app.utils.logging import logger
import json
import re

def sanitize_filename(filename: str) -> str:
    """Remove unsafe characters and limit length for filenames."""
    safe = re.sub(r'[^a-zA-Z0-9_-]', '_', Path(filename).stem)
    return safe[:50]  # prevent super long names

def make_file_label(filename: str, request_id: str) -> str:
    """Generate a short, human-readable label for logging and filenames."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_name = sanitize_filename(filename)
    return f"{timestamp}_{safe_name}_{request_id[:8]}"

def save_raw_text(request_id: str, text: str, original_filename: str = "document"):
    """Save extracted text for debugging with readable filenames."""
    try:
        label = make_file_label(original_filename, request_id)
        file_path = settings.raw_dir / f"{label}.txt"
        file_path.write_text(text, encoding="utf-8")
        logger.info("Saved raw text", extra={"file_label": label, "path": str(file_path)})
    except Exception as e:
        logger.warning(f"Failed to save raw text: {e}")

def save_parsed_result(request_id: str, data: dict, original_filename: str = "document"):
    """Save parsed result for audit with readable filenames."""
    try:
        label = make_file_label(original_filename, request_id)
        file_path = settings.parsed_dir / f"{label}.json"
        file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Saved parsed result", extra={"file_label": label, "path": str(file_path)})
    except Exception as e:
        logger.warning(f"Failed to save parsed result: {e}")

def save_raw_llm_response(request_id: str, data: dict, original_filename: str = "document"):
    """Save raw llm result for audit with readable filenames."""
    try:
        label = make_file_label(original_filename, request_id)
        file_path = settings.raw_llm_dir / f"{label}.json"
        file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Saved raw llm result", extra={"file_label": label, "path": str(file_path)})
    except Exception as e:
        logger.warning(f"Failed to save parsed result: {e}")