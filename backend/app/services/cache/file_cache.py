import hashlib
import json
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta
from app.utils.logging import logger


class DocumentCache:
    """
    File-backed cache for processed documents. Uses content hash as key and stores JSON in files.
    """

    def __init__(self, cache_dir: Path, cache_ttl_hours: int = 24):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = timedelta(hours=cache_ttl_hours)

    def _get_content_hash(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _get_cache_path(self, content_hash: str) -> Path:
        return self.cache_dir / f"{content_hash}.json"

    def get(self, content: bytes) -> Optional[dict]:
        content_hash = self._get_content_hash(content)
        cache_path = self._get_cache_path(content_hash)

        if not cache_path.exists():
            logger.info(f"Cache MISS for hash {content_hash[:8]}...")
            return None

        try:
            cache_data = json.loads(cache_path.read_text())
            cached_at = datetime.fromisoformat(cache_data["cached_at"])

            if datetime.now() - cached_at > self.cache_ttl:
                logger.info(f"Cache EXPIRED for hash {content_hash[:8]}...")
                cache_path.unlink(missing_ok=True)
                return None

            logger.info(f"Cache HIT for hash {content_hash[:8]}...")
            return cache_data["result"]

        except Exception as e:
            logger.error(f"Cache read error: {e}")
            return None

    def set(self, content: bytes, result: dict):
        content_hash = self._get_content_hash(content)
        cache_path = self._get_cache_path(content_hash)

        cache_data = {
            "content_hash": content_hash,
            "cached_at": datetime.now().isoformat(),
            "result": result,
        }

        try:
            cache_path.write_text(json.dumps(cache_data, indent=2))
            logger.info(f"Cached result for hash {content_hash[:8]}...")
        except Exception as e:
            logger.error(f"Cache write error: {e}")

    def clear_expired(self):
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_data = json.loads(cache_file.read_text())
                cached_at = datetime.fromisoformat(cache_data["cached_at"])

                if datetime.now() - cached_at > self.cache_ttl:
                    cache_file.unlink(missing_ok=True)
                    count += 1
            except Exception as e:
                logger.error(f"Error cleaning cache file {cache_file}: {e}")

        if count > 0:
            logger.info(f"Cleared {count} expired cache entries")

        return count
