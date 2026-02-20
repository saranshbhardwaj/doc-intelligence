"""Unit tests for AnthropicUsageService.flatten_usage_data()."""
from app.services.anthropic_usage_service import AnthropicUsageService


def test_flatten_single_bucket_single_model():
    """Typical case: one day bucket, one model."""
    raw = {
        "data": [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-02T00:00:00Z",
                "results": [
                    {
                        "uncached_input_tokens": 100000,
                        "cache_creation": {
                            "ephemeral_1h_input_tokens": 500,
                            "ephemeral_5m_input_tokens": 200,
                        },
                        "cache_read_input_tokens": 50000,
                        "output_tokens": 30000,
                        "model": "claude-sonnet-4-5-20250929",
                    }
                ],
            }
        ],
        "has_more": False,
        "next_page": None,
    }
    records = AnthropicUsageService.flatten_usage_data(raw)
    assert len(records) == 1
    r = records[0]
    assert r["model"] == "claude-sonnet-4-5-20250929"
    assert r["input_tokens"] == 100000
    assert r["output_tokens"] == 30000
    assert r["cache_read_input_tokens"] == 50000
    assert r["cache_creation_input_tokens"] == 700  # 500 + 200


def test_flatten_multiple_buckets_aggregates():
    """Multiple time buckets for same model should aggregate."""
    raw = {
        "data": [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T12:00:00Z",
                "results": [
                    {
                        "uncached_input_tokens": 1000,
                        "cache_creation": {},
                        "cache_read_input_tokens": 500,
                        "output_tokens": 200,
                        "model": "claude-sonnet-4-5-20250929",
                    }
                ],
            },
            {
                "starting_at": "2025-01-01T12:00:00Z",
                "ending_at": "2025-01-02T00:00:00Z",
                "results": [
                    {
                        "uncached_input_tokens": 3000,
                        "cache_creation": {
                            "ephemeral_1h_input_tokens": 100,
                        },
                        "cache_read_input_tokens": 1500,
                        "output_tokens": 800,
                        "model": "claude-sonnet-4-5-20250929",
                    }
                ],
            },
        ],
    }
    records = AnthropicUsageService.flatten_usage_data(raw)
    assert len(records) == 1
    r = records[0]
    assert r["input_tokens"] == 4000
    assert r["output_tokens"] == 1000
    assert r["cache_read_input_tokens"] == 2000
    assert r["cache_creation_input_tokens"] == 100


def test_flatten_multiple_models():
    """Multiple models in same bucket produce separate records."""
    raw = {
        "data": [
            {
                "results": [
                    {
                        "uncached_input_tokens": 1000,
                        "cache_creation": {},
                        "cache_read_input_tokens": 0,
                        "output_tokens": 500,
                        "model": "claude-sonnet-4-5-20250929",
                    },
                    {
                        "uncached_input_tokens": 2000,
                        "cache_creation": {"ephemeral_5m_input_tokens": 50},
                        "cache_read_input_tokens": 100,
                        "output_tokens": 1000,
                        "model": "claude-haiku-3-5-20241022",
                    },
                ],
            }
        ],
    }
    records = AnthropicUsageService.flatten_usage_data(raw)
    assert len(records) == 2
    by_model = {r["model"]: r for r in records}
    assert by_model["claude-sonnet-4-5-20250929"]["input_tokens"] == 1000
    assert by_model["claude-haiku-3-5-20241022"]["input_tokens"] == 2000
    assert by_model["claude-haiku-3-5-20241022"]["cache_creation_input_tokens"] == 50


def test_flatten_empty_data():
    """Empty data array returns empty list."""
    assert AnthropicUsageService.flatten_usage_data({"data": []}) == []
    assert AnthropicUsageService.flatten_usage_data({}) == []


def test_flatten_none_values_treated_as_zero():
    """None values in token fields should be treated as 0."""
    raw = {
        "data": [
            {
                "results": [
                    {
                        "uncached_input_tokens": None,
                        "cache_creation": None,
                        "cache_read_input_tokens": None,
                        "output_tokens": None,
                        "model": "claude-sonnet-4-5-20250929",
                    }
                ],
            }
        ],
    }
    records = AnthropicUsageService.flatten_usage_data(raw)
    assert len(records) == 1
    r = records[0]
    assert r["input_tokens"] == 0
    assert r["output_tokens"] == 0
    assert r["cache_read_input_tokens"] == 0
    assert r["cache_creation_input_tokens"] == 0


def test_flatten_missing_fields_default_to_zero():
    """Missing fields in API response should default to 0."""
    raw = {
        "data": [
            {
                "results": [
                    {
                        "model": "claude-sonnet-4-5-20250929",
                    }
                ],
            }
        ],
    }
    records = AnthropicUsageService.flatten_usage_data(raw)
    assert len(records) == 1
    r = records[0]
    assert r["input_tokens"] == 0
    assert r["output_tokens"] == 0
    assert r["cache_read_input_tokens"] == 0
    assert r["cache_creation_input_tokens"] == 0
