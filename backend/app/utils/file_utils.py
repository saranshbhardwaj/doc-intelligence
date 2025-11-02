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

def save_raw_azure_output(request_id: str, data: dict, original_filename: str = "document"):
    """Save full Azure Document Intelligence output for future chunking.

    Stored separately so we can avoid re-calling Azure when generating chunks.
    """
    try:
        # Create dedicated directory logs/azure_raw if not present
        azure_dir = settings.log_dir / "azure_raw"
        azure_dir.mkdir(parents=True, exist_ok=True)
        label = make_file_label(original_filename, request_id)
        file_path = azure_dir / f"{label}.json"
        file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Saved raw Azure output", extra={"file_label": label, "path": str(file_path)})
    except Exception as e:
        logger.warning(f"Failed to save raw Azure output: {e}")


def save_chunks(request_id: str, chunks_data: dict, original_filename: str = "document"):
    """Save chunking output for debugging chunking strategies.

    Args:
        request_id: Unique request ID
        chunks_data: Dictionary with 'chunks', 'strategy', 'metadata' keys
        original_filename: Original PDF filename
    """
    try:
        label = make_file_label(original_filename, request_id)
        file_path = settings.chunks_dir / f"{label}_chunks.json"
        file_path.write_text(json.dumps(chunks_data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Saved chunks", extra={"file_label": label, "chunk_count": len(chunks_data.get("chunks", []))})
    except Exception as e:
        logger.warning(f"Failed to save chunks: {e}")


def save_summaries(request_id: str, summaries_data: dict, original_filename: str = "document"):
    """Save cheap LLM summaries for verifying summarization quality.

    Args:
        request_id: Unique request ID
        summaries_data: Dictionary with 'summaries', 'model', 'metadata' keys
        original_filename: Original PDF filename
    """
    try:
        label = make_file_label(original_filename, request_id)
        file_path = settings.summaries_dir / f"{label}_summaries.json"
        file_path.write_text(json.dumps(summaries_data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Saved summaries", extra={"file_label": label, "summary_count": len(summaries_data.get("summaries", []))})
    except Exception as e:
        logger.warning(f"Failed to save summaries: {e}")


def save_combined_context(request_id: str, combined_text: str, metadata: dict, original_filename: str = "document"):
    """Save combined context sent to expensive LLM.

    This is useful for debugging what the final LLM actually sees.

    Args:
        request_id: Unique request ID
        combined_text: The combined narrative summaries + raw tables
        metadata: Metadata about compression ratio, chunk counts, etc.
        original_filename: Original PDF filename
    """
    try:
        label = make_file_label(original_filename, request_id)

        # Save text
        text_path = settings.combined_dir / f"{label}_context.txt"
        text_path.write_text(combined_text, encoding="utf-8")

        # Save metadata
        metadata_path = settings.combined_dir / f"{label}_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        logger.info(
            "Saved combined context",
            extra={
                "file_label": label,
                "context_chars": len(combined_text),
                "compression_ratio": metadata.get("compression_ratio")
            }
        )
    except Exception as e:
        logger.warning(f"Failed to save combined context: {e}")