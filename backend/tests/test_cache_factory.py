import tempfile
from pathlib import Path

from app.services.cache import create_cache, DocumentCache


def test_create_cache_file(tmp_path: Path):
    # Ensure factory returns a file-backed cache when use_redis_cache is False
    cache = create_cache(cache_dir=tmp_path, cache_ttl_hours=1)
    assert isinstance(cache, DocumentCache)

    sample = b"hello world"
    result = {"parsed": True, "text_len": len(sample)}
    cache.set(sample, result)
    loaded = cache.get(sample)
    assert loaded == result
