"""Service for fetching usage and cost data from Anthropic Admin API.

Uses httpx for async API calls to the Anthropic Usage & Cost endpoints.
Handles pagination and provides structured data for metrics and database storage.

Docs: https://docs.anthropic.com/en/docs/admin-api/usage-and-cost
"""
from __future__ import annotations
import httpx
from typing import Optional
from datetime import datetime, timedelta
from app.utils.logging import logger


class AnthropicUsageService:
    """Client for Anthropic Admin API (Usage & Cost reporting)."""

    BASE_URL = "https://api.anthropic.com/v1/organizations"
    ANTHROPIC_VERSION = "2023-06-01"

    def __init__(self, admin_api_key: str):
        """Initialize with Admin API key (sk-ant-admin-...)."""
        if not admin_api_key:
            raise ValueError("Anthropic Admin API key is required")

        self.admin_api_key = admin_api_key
        self.headers = {
            "anthropic-version": self.ANTHROPIC_VERSION,
            "x-api-key": self.admin_api_key,
        }

    async def fetch_usage_report(
        self,
        starting_at: str,
        ending_at: str,
        bucket_width: str = "1d",
        group_by: Optional[list[str]] = None,
    ) -> dict:
        """Fetch token usage from Anthropic Usage API.

        Args:
            starting_at: ISO 8601 timestamp (e.g., "2025-01-01T00:00:00Z")
            ending_at: ISO 8601 timestamp
            bucket_width: Time bucket size ("1m", "1h", "1d")
            group_by: Dimensions to group by (e.g., ["model", "workspace_id"])

        Returns:
            dict with structure (after pagination is resolved):
            {
                "data": [
                    {
                        "starting_at": "2025-01-01T00:00:00Z",
                        "ending_at": "2025-01-02T00:00:00Z",
                        "results": [
                            {
                                "uncached_input_tokens": 123456,
                                "cache_creation": {
                                    "ephemeral_1h_input_tokens": 456,
                                    "ephemeral_5m_input_tokens": 789
                                },
                                "cache_read_input_tokens": 500000,
                                "output_tokens": 234567,
                                "model": "claude-sonnet-4-5-20250929"
                            }
                        ]
                    }
                ],
                "has_more": false,
                "next_page": null
            }

            Note: Use flatten_usage_data() to convert this into flat per-model records.

        Raises:
            httpx.HTTPStatusError: If API returns non-200 status
            httpx.TimeoutException: If request times out
        """
        if group_by is None:
            group_by = ["model"]

        url = f"{self.BASE_URL}/usage_report/messages"
        base_params = [
            ("starting_at", starting_at),
            ("ending_at", ending_at),
            ("bucket_width", bucket_width),
        ]
        for dimension in group_by:
            base_params.append(("group_by[]", dimension))

        all_data = []
        has_more = True
        page_token = None

        async with httpx.AsyncClient(timeout=30.0) as client:
            while has_more:
                params = list(base_params)
                if page_token:
                    params.append(("page", page_token))

                try:
                    logger.info(
                        "Fetching Anthropic usage report",
                        extra={
                            "url": url,
                            "starting_at": starting_at,
                            "ending_at": ending_at,
                            "bucket_width": bucket_width,
                            "group_by": group_by,
                            "page": page_token or "first",
                        }
                    )

                    response = await client.get(url, headers=self.headers, params=params)
                    response.raise_for_status()

                    data = response.json()
                    all_data.extend(data.get("data", []))

                    has_more = data.get("has_more", False)
                    page_token = data.get("next_page")

                    logger.info(
                        "Fetched Anthropic usage page",
                        extra={
                            "items": len(data.get("data", [])),
                            "total_so_far": len(all_data),
                            "has_more": has_more,
                        }
                    )

                except httpx.HTTPStatusError as e:
                    logger.error(
                        "Anthropic usage API HTTP error",
                        extra={
                            "status": e.response.status_code,
                            "body": e.response.text[:500],
                        },
                        exc_info=True
                    )
                    raise

                except httpx.TimeoutException:
                    logger.error("Anthropic usage API timeout", exc_info=True)
                    raise

                except Exception:
                    logger.error("Anthropic usage API unexpected error", exc_info=True)
                    raise

        return {
            "data": all_data,
            "has_more": False,
            "next_page": None,
        }

    async def fetch_cost_report(
        self,
        starting_at: str,
        ending_at: str,
        group_by: Optional[list[str]] = None,
    ) -> dict:
        """Fetch cost data from Anthropic Cost API.

        Args:
            starting_at: ISO 8601 timestamp (e.g., "2025-01-01T00:00:00Z")
            ending_at: ISO 8601 timestamp
            group_by: Dimensions to group by (e.g., ["workspace_id", "description"])

        Returns:
            dict with structure:
            {
                "data": [
                    {
                        "time_bucket": "2025-01-01",
                        "description": "Claude API: claude-sonnet-4-5 | Inference Region: global",
                        "cost": "1234.567890"  # USD as string in lowest units (cents)
                    }
                ],
                "has_more": false,
                "next_page": null
            }

        Note:
            - Cost report only supports daily granularity (1d bucket_width)
            - Costs are in USD as decimal strings
            - description field can be parsed to extract model name

        Raises:
            httpx.HTTPStatusError: If API returns non-200 status
            httpx.TimeoutException: If request times out
        """
        if group_by is None:
            group_by = ["description"]

        url = f"{self.BASE_URL}/cost_report"
        base_params = [
            ("starting_at", starting_at),
            ("ending_at", ending_at),
        ]
        for dimension in group_by:
            base_params.append(("group_by[]", dimension))

        all_data = []
        has_more = True
        page_token = None

        async with httpx.AsyncClient(timeout=30.0) as client:
            while has_more:
                params = list(base_params)
                if page_token:
                    params.append(("page", page_token))

                try:
                    logger.info(
                        "Fetching Anthropic cost report",
                        extra={
                            "url": url,
                            "starting_at": starting_at,
                            "ending_at": ending_at,
                            "group_by": group_by,
                            "page": page_token or "first",
                        }
                    )

                    response = await client.get(url, headers=self.headers, params=params)
                    response.raise_for_status()

                    data = response.json()
                    all_data.extend(data.get("data", []))

                    has_more = data.get("has_more", False)
                    page_token = data.get("next_page")

                    logger.info(
                        "Fetched Anthropic cost page",
                        extra={
                            "items": len(data.get("data", [])),
                            "total_so_far": len(all_data),
                            "has_more": has_more,
                        }
                    )

                except httpx.HTTPStatusError as e:
                    logger.error(
                        "Anthropic cost API HTTP error",
                        extra={
                            "status": e.response.status_code,
                            "body": e.response.text[:500],
                        },
                        exc_info=True
                    )
                    raise

                except httpx.TimeoutException:
                    logger.error("Anthropic cost API timeout", exc_info=True)
                    raise

                except Exception:
                    logger.error("Anthropic cost API unexpected error", exc_info=True)
                    raise

        return {
            "data": all_data,
            "has_more": False,
            "next_page": None,
        }

    @staticmethod
    def parse_model_from_description(description: str) -> str:
        """Extract model name from cost report description field.

        Example:
            "Claude API: claude-sonnet-4-5 | Inference Region: global"
            -> "claude-sonnet-4-5"

        Args:
            description: Cost report description string

        Returns:
            Model name, or "unknown" if parsing fails
        """
        try:
            # Format: "Claude API: <model> | Inference Region: <region>"
            if "Claude API:" in description:
                parts = description.split("|")
                model_part = parts[0].strip()  # "Claude API: claude-sonnet-4-5"
                model_name = model_part.replace("Claude API:", "").strip()
                return model_name
            return "unknown"
        except Exception:
            return "unknown"

    @staticmethod
    def get_yesterday_time_range() -> tuple[str, str]:
        """Get ISO 8601 timestamps for yesterday (UTC).

        Returns:
            (starting_at, ending_at) tuple for yesterday's full day

        Example:
            If today is 2025-01-15, returns:
            ("2025-01-14T00:00:00Z", "2025-01-15T00:00:00Z")
        """
        now = datetime.utcnow()
        yesterday_start = (now - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        starting_at = yesterday_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        ending_at = today_start.strftime("%Y-%m-%dT%H:%M:%SZ")

        return starting_at, ending_at

    @staticmethod
    def flatten_usage_data(usage_report: dict) -> list[dict]:
        """Flatten nested usage API response into per-model records.

        The Usage API returns time buckets (data[]), each containing a results[]
        array with per-model token data. This method aggregates across all time
        buckets to produce one record per model.

        Field mappings:
            uncached_input_tokens -> input_tokens
            cache_creation.ephemeral_1h_input_tokens + ephemeral_5m_input_tokens -> cache_creation_input_tokens
            cache_read_input_tokens -> cache_read_input_tokens (unchanged)
            output_tokens -> output_tokens (unchanged)

        Args:
            usage_report: Raw response from fetch_usage_report()

        Returns:
            List of dicts with keys: model, input_tokens, output_tokens,
            cache_read_input_tokens, cache_creation_input_tokens
        """
        aggregated: dict[str, dict] = {}

        for bucket in usage_report.get("data", []):
            for result in bucket.get("results", []):
                model = result.get("model", "unknown")

                if model not in aggregated:
                    aggregated[model] = {
                        "model": model,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    }

                rec = aggregated[model]
                rec["input_tokens"] += result.get("uncached_input_tokens", 0) or 0
                rec["output_tokens"] += result.get("output_tokens", 0) or 0
                rec["cache_read_input_tokens"] += result.get("cache_read_input_tokens", 0) or 0

                cache_creation = result.get("cache_creation", {}) or {}
                rec["cache_creation_input_tokens"] += (
                    (cache_creation.get("ephemeral_1h_input_tokens", 0) or 0)
                    + (cache_creation.get("ephemeral_5m_input_tokens", 0) or 0)
                )

        return list(aggregated.values())
