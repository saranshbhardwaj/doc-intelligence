# backend/app/cache_utils.py
from pathlib import Path
from app.services.cache import DocumentCache
import json
from app.utils.logging import logger

def list_cache_entries(cache: DocumentCache):
    """
    List all cached files with timestamp and optionally first 8 chars of hash
    """
    entries = []
    for file in cache.cache_dir.glob("*.json"):
        try:
            data = json.loads(file.read_text())
            cached_at = data.get("cached_at")
            entries.append({
                "file": file.name,
                "cached_at": cached_at
            })
        except Exception as e:
            logger.error(f"Failed to read cache file {file}: {e}")
    return entries


def clear_all_cache(cache: DocumentCache):
    """
    Delete all cache entries
    """
    count = 0
    for file in cache.cache_dir.glob("*.json"):
        try:
            file.unlink()
            count += 1
        except Exception as e:
            logger.error(f"Failed to delete cache file {file}: {e}")
    logger.info(f"Cleared {count} cache entries")
    return count


def preload_cache_mock(cache: DocumentCache, file_bytes: bytes, mock_result: dict):
    """
    Preload a mock response for a given file content
    """
    cache.set(file_bytes, mock_result)
    logger.info(f"Preloaded mock cache for hash {cache._get_content_hash(file_bytes)[:8]}")
