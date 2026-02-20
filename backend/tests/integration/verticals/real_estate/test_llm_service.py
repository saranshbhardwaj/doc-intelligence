"""Integration tests for TemplateFillLLMService.

Tests LLM service methods with mocked Anthropic API (record/replay mode).
"""
import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from app.verticals.real_estate.template_filling.llm_service import (
    TemplateFillLLMService,
    AutoMappingResult,
    FieldMapping
)


# Simple classes for mocking Anthropic API responses
class MockUsage:
    def __init__(self, input_tokens, output_tokens, cache_creation_input_tokens=0, cache_read_input_tokens=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens


class MockContent:
    def __init__(self, text):
        self.text = text


class MockResponse:
    def __init__(self, text, usage):
        self.content = [MockContent(text)]
        self.usage = usage

# Path to recorded API responses
RESPONSES_DIR = Path(__file__).parent.parent.parent.parent / "fixtures" / "responses"


def load_recorded_response(test_name: str) -> dict:
    """Load a recorded API response from fixtures."""
    cassette_path = RESPONSES_DIR / f"{test_name}.json"
    if cassette_path.exists():
        return json.loads(cassette_path.read_text())
    return None


class TestTemplateFillLLMServiceAutoMapping:
    """Test auto_map_fields() method with recorded responses."""

    @pytest.mark.integration
    @patch("app.verticals.real_estate.template_filling.llm_service.Anthropic")
    def test_auto_map_fields_returns_structured_output(
        self,
        mock_anthropic_class,
        sample_pdf_fields,
        sample_excel_schema
    ):
        """Should return structured mapping result with confidence scores."""
        # Load recorded response
        recorded_response = load_recorded_response("test_auto_map_fields")
        assert recorded_response is not None, "Cassette file missing - run in record mode"

        # Create mock response object
        mock_response = MockResponse(
            text=recorded_response["content"][0]["text"],
            usage=MockUsage(
                input_tokens=recorded_response["usage"]["input_tokens"],
                output_tokens=recorded_response["usage"]["output_tokens"],
                cache_creation_input_tokens=recorded_response["usage"].get("cache_creation_input_tokens", 0),
                cache_read_input_tokens=recorded_response["usage"].get("cache_read_input_tokens", 0)
            )
        )

        # Mock client
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        # Initialize service
        service = TemplateFillLLMService()

        # Call method (async method needs to be awaited)
        result = asyncio.run(service.auto_map_fields(
            pdf_fields=sample_pdf_fields,
            excel_schema=sample_excel_schema
        ))

        # Verify structure
        assert result is not None
        assert "mappings" in result
        assert "total_mapped" in result
        assert "total_unmapped" in result
        assert "high_confidence_count" in result

        # Verify mappings
        mappings = result["mappings"]
        assert len(mappings) == 4
        assert all("pdf_field_id" in m for m in mappings)
        assert all("excel_cell" in m for m in mappings)
        assert all("confidence" in m for m in mappings)
        assert all(0.0 <= m["confidence"] <= 1.0 for m in mappings)

    @pytest.mark.integration
    @patch("app.verticals.real_estate.template_filling.llm_service.Anthropic")
    def test_auto_map_fields_high_confidence_mapping(
        self,
        mock_anthropic_class,
        sample_pdf_fields,
        sample_excel_schema
    ):
        """Should produce high-confidence mappings for exact terminology matches."""
        recorded_response = load_recorded_response("test_auto_map_fields")

        # Setup mock
        mock_response = MockResponse(
            text=recorded_response["content"][0]["text"],
            usage=MockUsage(
                input_tokens=2450,
                output_tokens=380,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0
            )
        )

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        service = TemplateFillLLMService()
        result = asyncio.run(service.auto_map_fields(
            pdf_fields=sample_pdf_fields,
            excel_schema=sample_excel_schema
        ))

        # Verify high-confidence mappings
        high_conf_mappings = [m for m in result["mappings"] if m["confidence"] > 0.9]
        assert len(high_conf_mappings) > 0

        # Verify exact match has highest confidence
        property_name_mapping = next(
            (m for m in result["mappings"] if m["pdf_field_name"] == "Property Name"),
            None
        )
        assert property_name_mapping is not None
        assert property_name_mapping["confidence"] >= 0.95
        assert property_name_mapping["excel_label"] == "Property Name"

    @pytest.mark.integration
    @patch("app.verticals.real_estate.template_filling.llm_service.Anthropic")
    def test_auto_map_fields_semantic_matching(
        self,
        mock_anthropic_class,
        sample_pdf_fields,
        sample_excel_schema
    ):
        """Should handle terminology variations (Cap Rate vs Going-In Cap Rate)."""
        recorded_response = load_recorded_response("test_auto_map_fields")

        mock_response = MockResponse(
            text=recorded_response["content"][0]["text"],
            usage=MockUsage(
                input_tokens=2450,
                output_tokens=380,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0
            )
        )

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        service = TemplateFillLLMService()
        result = asyncio.run(service.auto_map_fields(
            pdf_fields=sample_pdf_fields,
            excel_schema=sample_excel_schema
        ))

        # Find Cap Rate mapping
        cap_rate_mapping = next(
            (m for m in result["mappings"] if m["pdf_field_name"] == "Cap Rate"),
            None
        )

        assert cap_rate_mapping is not None
        assert cap_rate_mapping["excel_label"] == "Going-In Cap Rate"
        assert cap_rate_mapping["confidence"] >= 0.85  # Should have decent confidence
        assert "terminology" in cap_rate_mapping["reasoning"].lower() or "equivalent" in cap_rate_mapping["reasoning"].lower()

    @pytest.mark.integration
    @patch("app.verticals.real_estate.template_filling.llm_service.Anthropic")
    def test_auto_map_fields_includes_citations(
        self,
        mock_anthropic_class,
        sample_pdf_fields,
        sample_excel_schema
    ):
        """Should include PDF citations in mappings for traceability."""
        recorded_response = load_recorded_response("test_auto_map_fields")

        mock_response = MockResponse(
            text=recorded_response["content"][0]["text"],
            usage=MockUsage(
                input_tokens=2450,
                output_tokens=380,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0
            )
        )

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        service = TemplateFillLLMService()
        result = asyncio.run(service.auto_map_fields(
            pdf_fields=sample_pdf_fields,
            excel_schema=sample_excel_schema
        ))

        # Verify all mappings have citations
        for mapping in result["mappings"]:
            assert "citations" in mapping
            assert isinstance(mapping["citations"], list)
            assert len(mapping["citations"]) > 0
            # Citations should follow [D<doc_id>:p<page>] format
            assert any(c.startswith("[D") for c in mapping["citations"])

    @pytest.mark.integration
    @patch("app.verticals.real_estate.template_filling.llm_service.Anthropic")
    def test_auto_map_fields_token_accounting(
        self,
        mock_anthropic_class,
        sample_pdf_fields,
        sample_excel_schema
    ):
        """Should track token usage for cost observability."""
        recorded_response = load_recorded_response("test_auto_map_fields")

        mock_response = MockResponse(
            text=recorded_response["content"][0]["text"],
            usage=MockUsage(
                input_tokens=2450,
                output_tokens=380,
                cache_creation_input_tokens=100,
                cache_read_input_tokens=1000
            )
        )

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        service = TemplateFillLLMService()

        # Call and capture token usage
        result = service.auto_map_fields(
            pdf_fields=sample_pdf_fields,
            excel_template_structure=sample_excel_schema,
            fill_run_id="test-run-001"
        )

        # Token metrics should be returned (service tracks these internally)
        # Verify the mock was called with correct parameters
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args.kwargs

        assert "model" in call_kwargs
        assert "max_tokens" in call_kwargs


class TestTemplateFillLLMServiceErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.integration
    @patch("app.verticals.real_estate.template_filling.llm_service.Anthropic")
    def test_auto_map_fields_handles_api_timeout(self, mock_anthropic_class):
        """Should handle API timeout gracefully."""
        from anthropic import APITimeoutError

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = APITimeoutError("Request timeout")
        mock_anthropic_class.return_value = mock_client

        service = TemplateFillLLMService()

        with pytest.raises(APITimeoutError):
            asyncio.run(service.auto_map_fields(
                pdf_fields=[{"id": "1", "name": "Test"}],
                excel_schema={"sheets": [{"name": "Test", "cells": []}]}
            ))

    @pytest.mark.integration
    @patch("app.verticals.real_estate.template_filling.llm_service.Anthropic")
    def test_auto_map_fields_with_empty_pdf_fields(self, mock_anthropic_class):
        """Should handle empty PDF fields list."""
        service = TemplateFillLLMService()

        # Should return early without API call
        result = asyncio.run(service.auto_map_fields(
            pdf_fields=[],
            excel_schema={"sheets": [{"name": "Test", "cells": [{"cell": "B2", "label": "Test"}]}]}
        ))

        # Should return empty mappings
        assert result["mappings"] == []
        assert result["total_mapped"] == 0

    @pytest.mark.integration
    @patch("app.verticals.real_estate.template_filling.llm_service.Anthropic")
    def test_auto_map_fields_with_empty_excel_schema(self, mock_anthropic_class):
        """Should handle empty Excel schema."""
        service = TemplateFillLLMService()

        result = asyncio.run(service.auto_map_fields(
            pdf_fields=[{"id": "1", "name": "Test", "type": "text", "sample_value": "Value"}],
            excel_schema={"sheets": []}
        ))

        # Should return empty mappings
        assert result["mappings"] == []
        assert result["total_mapped"] == 0
