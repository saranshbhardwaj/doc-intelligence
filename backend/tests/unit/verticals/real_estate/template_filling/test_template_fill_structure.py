import pytest
from types import SimpleNamespace

from app.repositories.template_repository import _merge_extracted_data
from app.verticals.real_estate.template_filling.citations import (
    get_structure_routing_pages as _get_structure_routing_pages,
    resolve_pdf_field_page_info as _resolve_pdf_field_page_info,
    resolve_bbox_from_citations as _resolve_bbox_from_citations,
)
from app.verticals.real_estate.template_filling.excel.mapping_coordinator import (
    MappingCoordinator,
)
from app.verticals.real_estate.template_filling.llm_service import TemplateFillLLMService
from app.verticals.real_estate.template_filling.prompts.base import PromptPair
from app.verticals.real_estate.template_filling.prompts.v1 import (
    OMStructureDetectionResult,
    SchemaTableExtractionResult,
    V1PromptSet,
)
from app.verticals.real_estate.template_filling.source_map import (
    MARKET_CONTENT_PAGE,
    MARKET_TOC_PAGE,
    MARKET_WEAK_PAGE,
    STRUCTURE_HIGH_CONFIDENCE,
    STRUCTURE_LOW_CONFIDENCE,
    _classify_market_page_text,
    normalize_om_structure_with_pdf_fields,
)
from app.verticals.real_estate.template_filling.artifacts import (
    build_om_structure_artifact as _build_om_structure_artifact,
    build_structure_confidence_summary as _build_structure_confidence_summary,
)
from app.verticals.real_estate.template_filling.mapping_helpers import (
    build_narrative_pdf_field as _build_narrative_pdf_field,
    build_scalar_context_for_batch as _build_scalar_context_for_batch,
    consolidate_scalar_batches_by_context as _consolidate_scalar_batches_by_context,
)
from app.verticals.real_estate.template_filling.schema_planner import (
    _target_status,
)
from app.verticals.real_estate.template_filling.tasks import (
    _build_targeted_virtual_pdf_field,
    _mark_auto_mapping_exception,
    _plan_schema_targets_for_structure,
    _prepare_extracted_data_for_fill,
)


def test_structure_detection_prompt_requests_column_map_and_section_presence():
    prompt = V1PromptSet().build_detect_om_structure()

    assert prompt.response_model is OMStructureDetectionResult
    assert "column_map" in prompt.user_message
    assert "section_presence" in prompt.user_message
    assert "confidence" in prompt.user_message
    assert "citations" in prompt.user_message
    assert "evidence" in prompt.user_message


def test_structure_detection_prompt_uses_shared_threshold_constants():
    prompt = V1PromptSet().build_detect_om_structure()

    assert f"≥{STRUCTURE_HIGH_CONFIDENCE:.2f}" in prompt.user_message
    assert f"{STRUCTURE_LOW_CONFIDENCE:.2f}–" in prompt.user_message
    assert f"<{STRUCTURE_LOW_CONFIDENCE:.2f}" in prompt.user_message


def test_structure_detection_result_allows_partial_source_map_for_planner_degrade():
    parsed = {
        "column_map": {
            "current": {
                "present": True,
                "label": "CURRENT",
                "confidence": 0.95,
                "citations": ["[S1:p6]"],
            }
        },
        "section_presence": {
            "year1_operating_statement_present": {
                "present": True,
                "label": "YEAR 1",
                "confidence": 0.92,
                "citations": ["[S1:p6]"],
            }
        },
    }

    plan = _plan_schema_targets_for_structure(
        [
            {
                "id": "year1_expense",
                "sheet": "P&L",
                "value_cell": "E31",
                "fill_when": "year1_operating_statement_present",
                "requires_structure": ["column_map.year1"],
            }
        ],
        [],
        parsed,
    )

    assert plan["fields_to_extract"] == []
    assert plan["skipped_targets"][0]["skip_reason"] == "structure_key_missing"


def test_source_map_normalization_infers_sections_and_columns_from_detected_pdf_fields():
    structure = {
        "column_map": {
            "current": {"present": False, "confidence": 0.0, "citations": []},
            "year1": {"present": False, "confidence": 0.0, "citations": []},
            "pro_forma": {"present": False, "confidence": 0.0, "citations": []},
        },
        "section_presence": {},
    }
    pdf_fields = [
        {
            "source": "table_block",
            "name": "Operating Summary",
            "table_name": "Operating Summary",
            "table_columns": ["Line Item", "CURRENT", "YEAR-ONE", "PRO FORMA"],
            "table_rows": [
                ["Gross Potential Rent", "$271,200", "$285,740", "$360,741"],
                ["Total Operating Expenses", "$66,299", "$80,699", "$94,946"],
                ["Net Operating Income", "$177,453", "$202,790", "$246,813"],
            ],
            "citations": ["[S1:p6]"],
        },
        {
            "source": "table_block",
            "name": "Target Rent Analysis",
            "table_name": "Target Rent Analysis",
            "table_columns": ["Type", "# Units", "SqFt", "Current Rent"],
            "table_rows": [["5x10", "26", "50", "$75"]],
            "citations": ["[S2:p15]"],
        }
    ]

    augmented = normalize_om_structure_with_pdf_fields(structure, pdf_fields)

    sections = augmented["section_presence"]
    columns = augmented["column_map"]
    assert columns["current"]["present"] is True
    assert columns["year1"]["present"] is True
    assert columns["pro_forma"]["present"] is True
    assert sections["current_operating_statement_present"]["present"] is True
    assert sections["year1_operating_statement_present"]["present"] is True
    assert sections["pro_forma_operating_statement_present"]["present"] is True
    assert sections["unit_mix_present"]["present"] is True
    assert sections["unit_mix_present"]["citations"] == ["[S2:p15]"]

    plan = _plan_schema_targets_for_structure(
        [
            {
                "id": "year1_expense",
                "sheet": "P&L",
                "value_cell": "E31",
                "fill_when": ["year1_operating_statement_present"],
                "requires_structure": ["column_map.year1"],
            }
        ],
        [
            {
                "id": "actuals_unit_mix_storage_unit_mix",
                "sheet": "Actuals&UnitMix",
                "fill_when": ["unit_mix_present"],
                "requires_structure": [],
            }
        ],
        augmented,
    )

    assert [field["id"] for field in plan["fields_to_extract"]] == ["year1_expense"]
    assert [table["id"] for table in plan["tables_to_extract"]] == [
        "actuals_unit_mix_storage_unit_mix"
    ]
    assert plan["skipped_targets"] == []


def test_scalar_context_for_structure_scopes_to_cited_pages_before_budgeting():
    om_structure = {
        "section_presence": {
            "year1_operating_statement_present": {
                "present": True,
                "confidence": 0.95,
                "citations": ["[S1:p6]"],
            }
        },
        "column_map": {},
    }
    fields = [
        {
            "id": "page6-kv",
            "source": "key_value_pairs",
            "name": "Year 1 NOI",
            "extracted_value": "$202,790",
            "bbox": {"page": 6},
        },
        {
            "id": "page8-kv",
            "source": "key_value_pairs",
            "name": "Too far from Year 1",
            "extracted_value": "skip me",
            "bbox": {"page": 8},
        },
        {
            "id": "page30-kv",
            "source": "key_value_pairs",
            "name": "Unrelated Demographic",
            "extracted_value": "42",
            "bbox": {"page": 30},
        },
    ]
    scalar_batch = [
        {
            "id": "pnl_year1_noi",
            "source_basis": "om_operating_statement",
            "fill_when": ["year1_operating_statement_present"],
        }
    ]

    routed_fields, metadata = _build_scalar_context_for_batch(
        fields,
        om_structure,
        scalar_batch,
    )

    assert [field["id"] for field in routed_fields] == ["page6-kv"]
    assert metadata["routing_applied"] is True
    assert metadata["citation_pages"] == [6]


def test_pdf_field_page_info_prefers_bbox_then_page_range_then_regions_then_fallback():
    anchor, pages = _resolve_pdf_field_page_info(
        {
            "bbox": {"page": 12},
            "page_range": [10, 11],
            "bounding_regions": [{"page_number": 9}],
            "page_number": 8,
        }
    )

    assert anchor == 12
    assert pages == [12, 10, 11, 9, 8]

    anchor, pages = _resolve_pdf_field_page_info(
        {
            "page_range": [25, 30],
            "page_number": 25,
        }
    )

    assert anchor == 25
    assert pages == [25, 30]


def test_pdf_field_page_info_prefers_explicit_page_for_table_derived_fields():
    anchor, pages = _resolve_pdf_field_page_info(
        {
            "source": "table_block",
            "bbox": {"page": 20},
            "page_number": 26,
            "page_range": [26, 26],
        }
    )

    assert anchor == 26
    assert pages == [26, 20]


def test_structure_routing_pages_prefer_explicit_pages_then_range_then_citation_window():
    om_structure = {
        "section_presence": {
            "market_summary_present": {
                "present": True,
                "citations": ["[S353:p29]"],
                "routing_pages": [25, 26, 27, 28, 29, 30],
                "page_range": [25, 30],
            },
            "unit_mix_present": {
                "present": True,
                "citations": ["[S240:p15]"],
            },
            "rent_comps_present": {
                "present": True,
                "page_range": [22, 23],
                "citations": ["[S298:p22]"],
            },
        },
        "column_map": {},
    }

    assert _get_structure_routing_pages(om_structure, "market_summary_present") == [
        25,
        26,
        27,
        28,
        29,
        30,
    ]
    assert _get_structure_routing_pages(om_structure, "rent_comps_present") == [22, 23]
    assert _get_structure_routing_pages(om_structure, "unit_mix_present") == [14, 15, 16]


def test_scalar_context_uses_market_routing_pages_instead_of_single_citation_window():
    om_structure = {
        "section_presence": {
            "market_summary_present": {
                "present": True,
                "citations": ["[S353:p29]"],
                "routing_pages": [25, 26, 27, 28, 29, 30],
            }
        },
        "column_map": {},
    }
    fields = [
        {"id": "page26-population-table", "source": "table_block", "page_number": 26},
        {"id": "page29-employer-table", "source": "table_block", "page_number": 29},
        {"id": "page31-unrelated", "source": "table_block", "page_number": 31},
    ]

    routed_fields, metadata = _build_scalar_context_for_batch(
        fields,
        om_structure,
        [{"id": "napkin_population", "fill_when": ["market_summary_present"]}],
    )

    assert [field["id"] for field in routed_fields] == [
        "page26-population-table",
        "page29-employer-table",
    ]
    assert metadata["routing_pages"] == [25, 26, 27, 28, 29, 30]
    assert metadata["citation_pages"] == [29]


def test_market_source_map_normalization_adds_multi_page_routing_range():
    normalized = normalize_om_structure_with_pdf_fields(
        {
            "column_map": {},
            "section_presence": {
                "market_summary_present": {
                    "present": True,
                    "label": "Market Summary",
                    "confidence": 0.95,
                    "citations": ["[S353:p29]"],
                }
            },
        },
        [
            {
                "id": "narrative_block_300",
                "source": "narrative_block",
                "section": "Market Overview",
                "full_text": "Tulsa metro highlights and demographics",
                "page_number": 25,
                "citations": ["[S300:p25]"],
            },
            {
                "id": "tbl_block_310",
                "source": "table_block",
                "table_name": "Population and Households by Income",
                "table_columns": ["Population", "1 Mile", "3 Miles", "5 Miles"],
                "table_rows": [["2023 Estimate", "10,509", "63,110", "153,689"]],
                "page_number": 26,
                "citations": ["[S310:p26]"],
            },
            {
                "id": "tbl_block_320",
                "source": "table_block",
                "table_name": "Population Profile",
                "table_columns": ["Population 25+ by Education Level", "Housing Units", "1 Mile", "3 Miles", "5 Miles"],
                "table_rows": [["2023 Estimate Population Age 25+", "6,162", "38,240", "101,066"]],
                "page_number": 27,
                "citations": ["[S320:p27]"],
            },
            {
                "id": "narrative_block_330",
                "source": "narrative_block",
                "section": "Demographics",
                "full_text": "Population, income, employment, housing and education",
                "page_number": 28,
                "citations": ["[S330:p28]"],
            },
            {
                "id": "tbl_block_353",
                "source": "table_block",
                "table_name": "Major Employers",
                "table_columns": ["Major Employers", "Employees"],
                "table_rows": [["American Airlines", "5,200"]],
                "page_number": 29,
                "citations": ["[S353:p29]"],
            },
            {
                "id": "narrative_block_360",
                "source": "narrative_block",
                "section": "Demographics Map",
                "full_text": "1 mile 3 miles 5 miles demographics map",
                "page_number": 30,
                "citations": ["[S360:p30]"],
            },
        ],
    )

    market_entry = normalized["section_presence"]["market_summary_present"]
    assert market_entry["citations"] == ["[S353:p29]"]
    assert market_entry["page_range"] == [25, 30]
    assert market_entry["routing_pages"] == [25, 26, 27, 28, 29, 30]


def test_market_page_classifier_distinguishes_toc_content_and_heading_only():
    toc_text = (
        "TABLE OF CONTENTS 5 SECTION 1 Executive Summary 9 SECTION 2 Property Information 14 "
        "SECTION 3 Financial Analysis 19 SECTION 4 Rent Comparables 24 SECTION 5 Market Overview"
    ).lower()
    content_text = (
        "Population Profile 2023 Estimate 153,689 households median household income "
        "$41,726 employment major employers 1 mile 3 miles 5 miles"
    ).lower()
    heading_text = "Market Overview Demographics".lower()

    assert _classify_market_page_text(toc_text) == MARKET_TOC_PAGE
    assert _classify_market_page_text(content_text) == MARKET_CONTENT_PAGE
    assert _classify_market_page_text(heading_text) == MARKET_WEAK_PAGE


def test_market_source_map_routing_ignores_toc_market_mentions():
    normalized = normalize_om_structure_with_pdf_fields(
        {
            "column_map": {},
            "section_presence": {
                "market_summary_present": {
                    "present": True,
                    "label": "Market Summary",
                    "confidence": 0.95,
                    "citations": ["[S353:p29]"],
                }
            },
        },
        [
            {
                "id": "toc_page_4",
                "source": "narrative_block",
                "section": "Table of Contents",
                "full_text": (
                    "TABLE OF CONTENTS 5 SECTION 1 Executive Summary 9 "
                    "SECTION 2 Property Information 14 SECTION 3 Financial Analysis 19 "
                    "SECTION 4 Rent Comparables 24 SECTION 5 Market Overview"
                ),
                "page_number": 4,
                "citations": ["[S4:p4]"],
            },
            {
                "id": "market_page_25",
                "source": "narrative_block",
                "section": "Market Overview",
                "full_text": (
                    "Tulsa metro highlights economy demographics population 1M "
                    "households 407K median household income $59,300"
                ),
                "page_number": 25,
                "citations": ["[S300:p25]"],
            },
            {
                "id": "market_page_26",
                "source": "table_block",
                "table_name": "Population and Households by Income",
                "table_columns": ["Population", "Households", "Household Income", "1 Mile", "3 Miles", "5 Miles"],
                "table_rows": [["2023 Estimate", "10,509", "63,110", "153,689"]],
                "page_number": 26,
                "citations": ["[S310:p26]"],
            },
            {
                "id": "market_page_27",
                "source": "table_block",
                "table_name": "Population Profile",
                "table_columns": ["Population Profile", "Education Level", "Housing Units", "1 Mile", "3 Miles"],
                "table_rows": [["2023 Estimate Population Age 25+", "6,162", "38,240", "101,066"]],
                "page_number": 27,
                "citations": ["[S320:p27]"],
            },
            {
                "id": "market_page_28",
                "source": "narrative_block",
                "section": "Demographics",
                "full_text": (
                    "Population employment households housing income education. "
                    "The median household income is $41,726 and per capita income is $28,049."
                ),
                "page_number": 28,
                "citations": ["[S330:p28]"],
            },
            {
                "id": "market_page_29",
                "source": "table_block",
                "table_name": "Major Employers",
                "table_columns": ["Major Employers", "Employees"],
                "table_rows": [["American Airlines", "5,200"]],
                "page_number": 29,
                "citations": ["[S353:p29]"],
            },
            {
                "id": "market_page_30",
                "source": "narrative_block",
                "section": "Demographics Map",
                "full_text": "Market overview demographics radius map 1 mile 3 miles 5 miles",
                "page_number": 30,
                "citations": ["[S360:p30]"],
            },
        ],
    )

    market_entry = normalized["section_presence"]["market_summary_present"]
    assert market_entry["page_range"] == [25, 30]
    assert market_entry["routing_pages"] == [25, 26, 27, 28, 29, 30]
    assert 4 not in market_entry["routing_pages"]
    assert market_entry["routing_source"] == "market_section_cluster"


def test_market_source_map_repairs_toc_anchor_to_nearest_content_cluster():
    normalized = normalize_om_structure_with_pdf_fields(
        {
            "column_map": {},
            "section_presence": {
                "market_summary_present": {
                    "present": True,
                    "label": "Market Summary",
                    "confidence": 0.9,
                    "citations": ["[S4:p4]"],
                }
            },
        },
        [
            {
                "id": "toc_page_4",
                "source": "narrative_block",
                "section": "Table of Contents",
                "full_text": "TABLE OF CONTENTS SECTION 5 Market Overview 25",
                "page_number": 4,
                "citations": ["[S4:p4]"],
            },
            {
                "id": "market_page_25",
                "source": "narrative_block",
                "section": "Market Overview",
                "full_text": "Metro highlights demographics population households median household income $59,300",
                "page_number": 25,
                "citations": ["[S300:p25]"],
            },
            {
                "id": "market_page_26",
                "source": "table_block",
                "table_name": "Population",
                "table_columns": ["Population", "1 Mile", "3 Miles", "5 Miles"],
                "table_rows": [["2023 Estimate", "10,509", "63,110", "153,689"]],
                "page_number": 26,
                "citations": ["[S310:p26]"],
            },
        ],
    )

    market_entry = normalized["section_presence"]["market_summary_present"]
    assert market_entry["page_range"] == [25, 26]
    assert market_entry["routing_pages"] == [25, 26]
    assert market_entry["routing_source"] == "market_section_cluster_repaired_anchor"


def test_source_map_normalization_does_not_treat_current_rent_unit_mix_as_operating_current_column():
    normalized = normalize_om_structure_with_pdf_fields(
        {"column_map": {}, "section_presence": {}},
        [
            {
                "source": "table_block",
                "table_name": "Unit Mix by Type",
                "table_columns": ["Type", "# Units", "SqFt", "Current Rent"],
                "table_rows": [["5x10", "26", "50", "$75"]],
                "citations": ["[S2:p15]"],
            }
        ],
    )

    assert normalized["section_presence"]["unit_mix_present"]["present"] is True
    assert normalized["column_map"]["current"]["present"] is False


def test_scalar_context_for_always_fields_keeps_full_pool_before_budgeting():
    fields = [
        {"id": "cover", "source": "key_value_pairs", "bbox": {"page": 1}},
        {"id": "market", "source": "key_value_pairs", "bbox": {"page": 18}},
    ]

    routed_fields, metadata = _build_scalar_context_for_batch(
        fields,
        {"section_presence": {}, "column_map": {}},
        [{"id": "property_name", "source_basis": "om_property_summary", "fill_when": ["always"]}],
    )

    assert [field["id"] for field in routed_fields] == ["cover", "market"]
    assert metadata["routing_applied"] is False


def test_scalar_batch_consolidation_merges_only_exact_context_matches():
    consolidated = _consolidate_scalar_batches_by_context(
        [
            {
                "batch_key": "operating:current",
                "fields": [{"id": "current_noi"}],
                "context": [{"id": "ctx-1"}, {"id": "ctx-2"}],
                "budget": {"citation_pages": [16]},
            },
            {
                "batch_key": "operating:pro_forma",
                "fields": [{"id": "proforma_noi"}],
                "context": [{"id": "ctx-1"}, {"id": "ctx-2"}],
                "budget": {"citation_pages": [16]},
            },
            {
                "batch_key": "market:summary",
                "fields": [{"id": "population"}],
                "context": [{"id": "ctx-3"}],
                "budget": {"citation_pages": [29]},
            },
        ]
    )

    assert len(consolidated) == 2
    merged = consolidated[0]
    assert merged["batch_keys"] == ["operating:current", "operating:pro_forma"]
    assert [field["id"] for field in merged["fields"]] == ["current_noi", "proforma_noi"]
    assert [field["id"] for field in merged["context"]] == ["ctx-1", "ctx-2"]


def test_scalar_batch_consolidation_does_not_merge_same_pages_with_different_contexts():
    consolidated = _consolidate_scalar_batches_by_context(
        [
            {
                "batch_key": "operating:current",
                "fields": [{"id": "current_noi"}],
                "context": [{"id": "ctx-1"}, {"id": "ctx-2"}],
                "budget": {"citation_pages": [16]},
            },
            {
                "batch_key": "operating:year1",
                "fields": [{"id": "year1_noi"}],
                "context": [{"id": "ctx-1"}],
                "budget": {"citation_pages": [16]},
            },
        ]
    )

    assert len(consolidated) == 2
    assert consolidated[0]["batch_keys"] == ["operating:current"]
    assert consolidated[1]["batch_keys"] == ["operating:year1"]


def test_structure_confidence_summary_collects_low_keys():
    structure = {
        "column_map": {
            "current": {"present": True, "confidence": 0.91},
            "year1": {"present": True, "confidence": 0.55},
        },
        "section_presence": {
            "unit_mix_present": {"present": True, "confidence": 0.8},
        },
    }

    summary = _build_structure_confidence_summary(structure)

    assert summary["min_confidence"] == 0.55
    assert summary["mean_confidence"] == 0.7533
    assert summary["low_confidence_keys"] == ["column_map.year1"]


def test_om_structure_artifact_normalizes_citations_for_clickable_badges():
    artifact = _build_om_structure_artifact(
        {
            "column_map": {
                "current": {
                    "present": True,
                    "label": "CURRENT",
                    "confidence": 0.95,
                    "citations": ["S219:p6"],
                }
            },
            "section_presence": {
                "rent_comps_present": {
                    "present": True,
                    "label": "Rent Comps",
                    "confidence": 0.9,
                    "citations": ["S298:p22", "[S303:p22]"],
                }
            },
        },
        "model-a",
    )

    assert artifact["effective"]["column_map"]["current"]["citations"] == ["[D219:p6]"]
    assert artifact["original"]["section_presence"]["rent_comps_present"]["citations"] == [
        "[D298:p22]",
        "[D303:p22]",
    ]


def test_narrative_pdf_field_preserves_page_number_for_cover_page_routing():
    field = _build_narrative_pdf_field(
        field_id_counter=77,
        narrative_text="Tulsa Self Storage Units and Parking",
        section_heading="Cover",
        narrative_page=1,
    )

    assert field["id"] == "narrative_block_77"
    assert field["page_number"] == 1
    assert field["citations"] == ["[S77:p1]"]


def test_pre_fill_planner_skips_missing_section_and_low_confidence_structure_key():
    fields = [
        {
            "id": "current_expense",
            "sheet": "Actuals&UnitMix",
            "value_cell": "C19",
            "fill_when": "current_operating_statement_present",
            "requires_structure": ["column_map.current"],
        },
        {
            "id": "year1_expense",
            "sheet": "P&L",
            "value_cell": "E31",
            "fill_when": "year1_operating_statement_present",
            "requires_structure": ["column_map.year1"],
        },
        {
            "id": "property_name",
            "sheet": "DASHBOARD",
            "value_cell": "C3",
            "fill_when": "always",
        },
    ]
    structure = {
        "column_map": {
            "current": {"present": True, "confidence": 0.92},
            "year1": {"present": True, "confidence": 0.52},
        },
        "section_presence": {
            "current_operating_statement_present": {"present": False, "confidence": 0.95},
            "year1_operating_statement_present": {"present": True, "confidence": 0.95},
        },
    }

    plan = _plan_schema_targets_for_structure(fields, [], structure)

    assert [f["id"] for f in plan["fields_to_extract"]] == ["property_name"]
    status_by_id = {item["target_id"]: item for item in plan["skipped_targets"]}
    assert status_by_id["current_expense"]["skip_reason"] == "missing_section"
    assert status_by_id["year1_expense"]["skip_reason"] == "low_structure_confidence"


def test_pre_fill_planner_marks_mid_confidence_for_review_without_skipping():
    fields = [
        {
            "id": "year1_expense",
            "sheet": "P&L",
            "value_cell": "E31",
            "fill_when": "year1_operating_statement_present",
            "requires_structure": ["column_map.year1"],
        }
    ]
    structure = {
        "column_map": {
            "year1": {"present": True, "confidence": 0.72},
        },
        "section_presence": {
            "year1_operating_statement_present": {"present": True, "confidence": 0.95},
        },
    }

    plan = _plan_schema_targets_for_structure(fields, [], structure)

    assert [f["id"] for f in plan["fields_to_extract"]] == ["year1_expense"]
    assert plan["review_required_targets"] == [
        {
            "excel_sheet": "P&L",
            "excel_cell": "E31",
            "target_id": "year1_expense",
            "target_type": "field",
            "review_reason": "mid_structure_confidence",
            "structure_key": "column_map.year1",
            "confidence": 0.72,
        }
    ]


def test_pre_fill_planner_treats_multiple_fill_when_values_as_fallbacks():
    fields = [
        {
            "id": "actuals_taxes",
            "sheet": "Actuals&UnitMix",
            "value_cell": "C19",
            "fill_when": ["t12_present", "current_operating_statement_present"],
        }
    ]
    structure = {
        "section_presence": {
            "t12_present": {"present": False, "confidence": 0.95},
            "current_operating_statement_present": {"present": True, "confidence": 0.95},
        }
    }

    plan = _plan_schema_targets_for_structure(fields, [], structure)

    assert [f["id"] for f in plan["fields_to_extract"]] == ["actuals_taxes"]
    assert plan["skipped_targets"] == []


def test_pre_fill_planner_treats_multiple_structure_keys_as_fallbacks():
    fields = [
        {
            "id": "forward_expense",
            "sheet": "P&L",
            "value_cell": "E31",
            "fill_when": ["year1_operating_statement_present", "pro_forma_operating_statement_present"],
            "requires_structure": ["column_map.year1", "column_map.pro_forma"],
        }
    ]
    structure = {
        "column_map": {
            "year1": {"present": False, "confidence": 0.95},
            "pro_forma": {"present": True, "confidence": 0.9},
        },
        "section_presence": {
            "year1_operating_statement_present": {"present": False, "confidence": 0.95},
            "pro_forma_operating_statement_present": {"present": True, "confidence": 0.95},
        },
    }

    plan = _plan_schema_targets_for_structure(fields, [], structure)

    assert [f["id"] for f in plan["fields_to_extract"]] == ["forward_expense"]
    assert plan["skipped_targets"] == []


def test_pre_fill_planner_skips_missing_structure_key():
    fields = [
        {
            "id": "year1_expense",
            "sheet": "P&L",
            "value_cell": "E31",
            "fill_when": "year1_operating_statement_present",
            "requires_structure": ["column_map.year1"],
        }
    ]
    structure = {
        "column_map": {},
        "section_presence": {
            "year1_operating_statement_present": {"present": True, "confidence": 0.95},
        },
    }

    plan = _plan_schema_targets_for_structure(fields, [], structure)

    assert plan["fields_to_extract"] == []
    assert plan["skipped_targets"][0]["skip_reason"] == "structure_key_missing"


def test_target_status_rejects_unknown_skip_reason_and_prevents_shadowing():
    target = {"id": "field_a", "sheet": "Sheet1", "value_cell": "A1"}

    status = _target_status(
        target,
        "field",
        "missing_section",
        target_id="shadow",
        excel_cell="Z9",
        structure_key="section_presence.t12_present",
    )

    assert status["target_id"] == "field_a"
    assert status["excel_cell"] == "A1"
    assert status["structure_key"] == "section_presence.t12_present"

    with pytest.raises(ValueError, match="Unknown skip reason"):
        _target_status(target, "field", "bad_reason")


def test_extract_schema_field_prompt_uses_trimmed_source_map_context():
    full_structure = {
        "column_map": {
            "year1": {
                "present": True,
                "label": "YEAR 1",
                "confidence": 0.92,
                "citations": ["[S1:p6]"],
                "evidence": "YEAR 1 appears in the operating table",
            }
        },
        "section_presence": {
            "year1_operating_statement_present": {
                "present": True,
                "label": "Financial Summary",
                "confidence": 0.9,
                "citations": ["[S2:p7]"],
                "evidence": "Financial Summary table",
            }
        },
    }
    prompt = V1PromptSet().build_extract_schema_fields(
        "[]",
        [{"id": "pnl_year1_personnel_expense", "sheet": "P&L", "value_cell": "E32"}],
        om_structure=full_structure,
    )

    # Source Map goes in user_message so system_prompt stays static (cacheable).
    assert '"label": "YEAR 1"' in prompt.user_message
    assert '"confidence": 0.92' in prompt.user_message
    # trim_om_structure_for_prompt strips citations/evidence — only labels/confidence included.
    assert "[S1:p6]" not in prompt.user_message
    assert '"evidence"' not in prompt.user_message
    assert "YEAR 1" not in prompt.system_prompt
    assert "Use the most specific citation token available for the exact value" in prompt.user_message
    assert "If extracting an expense field" in prompt.user_message


def test_extract_table_prompt_uses_trimmed_source_map_context():
    full_structure = {
        "column_map": {
            "current": {
                "present": True,
                "label": "CURRENT",
                "confidence": 0.93,
                "citations": ["[S1:p16]"],
                "evidence": "CURRENT operating column",
            }
        },
        "section_presence": {
            "unit_mix_present": {
                "present": True,
                "label": "Unit Mix",
                "confidence": 0.96,
                "citations": ["[S2:p15]"],
                "evidence": "Unit mix table",
            }
        },
    }

    prompt = V1PromptSet().build_extract_table_values_rag(
        "[]",
        [{"table_id": "actuals_unit_mix_storage_unit_mix"}],
        "headers",
        om_structure=full_structure,
    )

    # Source Map goes in user_message so system_prompt stays static (cacheable).
    assert '"label": "CURRENT"' in prompt.user_message
    assert '"confidence": 0.93' in prompt.user_message
    assert "[S1:p16]" not in prompt.user_message
    assert '"evidence"' not in prompt.user_message
    assert "CURRENT" not in prompt.system_prompt
    assert "Use the most specific citation token available for the exact value" in prompt.user_message


def test_shared_azure_context_block_is_stable_across_source_map_and_scalar_calls():
    prompt_set = V1PromptSet()
    context_json = '[{"id":"table_1","source":"table_block"}]'

    source_map_context = prompt_set.build_azure_di_context_block(context_json)
    scalar_context = prompt_set.build_azure_di_context_block(context_json)

    assert source_map_context == scalar_context
    assert context_json in source_map_context


@pytest.mark.asyncio
async def test_table_extraction_service_passes_om_structure_to_prompt_builder():
    captured = {}

    class PromptSpy:
        version = "v1"

        def build_extract_table_values_rag(
            self,
            context_json,
            table_requests,
            header_equivalents,
            om_structure=None,
        ):
            captured["om_structure"] = om_structure
            return PromptPair(
                system_prompt="system",
                user_message="user",
                response_model=SchemaTableExtractionResult,
            )

        def build_azure_di_context_block(self, context_json):
            return f"context: {context_json}"

    class MessageSpy:
        def create(self, **_kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        text='{"results":[],"total_tables":0,"total_rows":0}'
                    )
                ],
                usage=SimpleNamespace(
                    input_tokens=0,
                    output_tokens=0,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=0,
                ),
            )

    service = TemplateFillLLMService.__new__(TemplateFillLLMService)
    service.prompts = PromptSpy()
    service.client = SimpleNamespace(messages=MessageSpy())
    service.model = "test-model"
    service.max_tokens = 1024
    service.capture_io_log = False
    service._io_log_repo = None
    service._record_llm_metrics = lambda *_args, **_kwargs: None

    structure = {"column_map": {"current": {"present": True, "confidence": 0.9}}}
    await service.extract_schema_table_values_rag_batch(
        [
            {
                "id": "table_a",
                "sheet": "Actuals&UnitMix",
                "data_start_row": 5,
                "data_end_row": 5,
                "columns": [{"excel_column": "G", "header": "Type"}],
            }
        ],
        [{"source": "table_block", "type": "table", "table_rows": []}],
        om_structure=structure,
    )

    assert captured["om_structure"] is structure


def test_table_context_excludes_targeted_schema_virtual_fields():
    service = TemplateFillLLMService.__new__(TemplateFillLLMService)

    context = service._build_table_context_from_pdf_fields(
        [
            {"source": "table_block", "name": "Unit Mix", "table_rows": [["5x10"]]},
            {
                "source": "targeted_schema",
                "name": "pnl_year1_personnel_expense",
                "extracted_value": "$17,250",
            },
        ]
    )

    assert len(context) == 1
    assert "Unit Mix" in context[0]["text"]


def test_table_context_preserves_global_citations_for_table_fields():
    service = TemplateFillLLMService.__new__(TemplateFillLLMService)

    context = service._build_table_context_from_pdf_fields(
        [
            {
                "id": "tbl_block_240",
                "source": "table_block",
                "name": "Unit Mix",
                "page_number": 15,
                "table_columns": ["Type", "# Units", "SqFt", "Current Rent"],
                "table_rows": [{"Type": "5x10", "# Units": 26, "SqFt": 50, "Current Rent": 75}],
                "citations": ["[S240:p15]"],
            }
        ]
    )

    assert context[0]["citations"] == ["[S240:p15]"]
    assert "Use citation [S240:p15]" in context[0]["text"]


def test_table_row_citation_repair_replaces_local_token_with_global_same_page():
    service = TemplateFillLLMService.__new__(TemplateFillLLMService)
    context_payload = [
        {"page_number": 3, "citations": ["[S1:p3]"]},
        {"page_number": 15, "citations": ["[S240:p15]"]},
    ]
    table_result = {
        "results": [
            {
                "table_id": "unit_mix",
                "rows": [
                    {
                        "row_index": 0,
                        "values": {"K": "75"},
                        "citations": ["[S1:p15]"],
                    }
                ],
            }
        ]
    }

    service._repair_table_result_citations(table_result, context_payload)

    assert table_result["results"][0]["rows"][0]["citations"] == ["[S240:p15]"]


def test_auto_mapping_exception_uses_mark_error_for_sse_termination():
    class RepoSpy:
        def __init__(self):
            self.updated = None

        def update_fill_run(self, fill_run_id, **kwargs):
            self.updated = {"fill_run_id": fill_run_id, **kwargs}

    class TrackerSpy:
        def __init__(self):
            self.error = None

        def mark_error(self, **kwargs):
            self.error = kwargs

    repo = RepoSpy()
    tracker = TrackerSpy()

    _mark_auto_mapping_exception(repo, tracker, "run-1", RuntimeError("source map failed"))

    assert repo.updated["status"] == "failed"
    assert repo.updated["error_stage"] == "auto_mapping"
    assert tracker.error["error_stage"] == "auto_mapping"
    assert tracker.error["error_message"] == "source map failed"


def test_om_structure_artifact_keeps_original_and_effective_independent():
    detected = {
        "column_map": {
            "year1": {"present": True, "label": "YEAR 1", "confidence": 0.91}
        },
        "section_presence": {},
    }

    artifact = _build_om_structure_artifact(detected, "model-a")
    artifact["effective"]["column_map"]["year1"]["label"] = "Edited"

    assert artifact["original"]["column_map"]["year1"]["label"] == "YEAR 1"
    assert artifact["effective"]["column_map"]["year1"]["label"] == "Edited"


def test_merge_extracted_data_preserves_existing_values_and_adds_source_map():
    merged = _merge_extracted_data(
        {
            "llm_extracted": {"field_a": {"value": "A"}},
            "manual_edits": {"Sheet1": {"A1": {"value": "manual"}}},
        },
        {"om_structure": {"effective": {"column_map": {}}}},
    )

    assert merged["llm_extracted"]["field_a"]["value"] == "A"
    assert merged["manual_edits"]["Sheet1"]["A1"]["value"] == "manual"
    assert merged["om_structure"]["effective"] == {"column_map": {}}


def test_prepare_extracted_data_for_fill_preserves_om_structure():
    prepared = _prepare_extracted_data_for_fill(
        {
            "om_structure": {
                "effective": {
                    "column_map": {
                        "year1": {"present": True, "label": "YEAR-ONE"}
                    }
                }
            },
            "llm_extracted": {
                "existing_field": {"value": "already here", "user_edited": False}
            },
            "manual_edits": {
                "DASHBOARD": {
                    "C3": {"value": "Manual name", "user_edited": True}
                }
            },
        },
        {
            "pdf_fields": [
                {
                    "id": "new_field",
                    "extracted_value": "New value",
                    "confidence": 0.91,
                    "citations": ["[S1:p1]"],
                }
            ]
        },
    )

    assert prepared["om_structure"]["effective"]["column_map"]["year1"]["label"] == "YEAR-ONE"
    assert prepared["llm_extracted"]["existing_field"]["value"] == "already here"
    assert prepared["llm_extracted"]["new_field"]["value"] == "New value"
    assert prepared["manual_edits"]["DASHBOARD"]["C3"]["value"] == "Manual name"


def test_resolve_bbox_from_citations_requires_matching_source_and_page():
    citation_context = {
        "citations": [
            {
                "source_index": 240,
                "page": 15,
                "bbox": {"page": 15, "x0": 1, "y0": 2, "x1": 3, "y1": 4},
            },
            {
                "source_index": 241,
                "page": 16,
                "bbox": {"page": 16, "x0": 5, "y0": 6, "x1": 7, "y1": 8},
            },
        ]
    }

    assert _resolve_bbox_from_citations(["[S240:p15]"], citation_context) == {
        "page": 15,
        "x0": 1,
        "y0": 2,
        "x1": 3,
        "y1": 4,
    }
    assert _resolve_bbox_from_citations(["[S240:p16]"], citation_context) is None


def test_targeted_table_virtual_field_copies_bbox_from_citation_context():
    virtual_field = _build_targeted_virtual_pdf_field(
        {
            "pdf_field_id": "targeted_table_unit_mix_G10",
            "pdf_field_name": "actuals_unit_mix_storage_unit_mix:G10",
            "data_type": "text",
            "extracted_value": "10 x 15",
            "confidence": 0.95,
            "citations": ["[S240:p15]"],
            "reasoning": "Extracted from Unit Mix table",
        },
        {
            "citations": [
                {
                    "source_index": 240,
                    "page": 15,
                    "bbox": {"page": 15, "x0": 1, "y0": 2, "x1": 3, "y1": 4},
                }
            ]
        },
    )

    assert virtual_field["bbox"] == {"page": 15, "x0": 1, "y0": 2, "x1": 3, "y1": 4}
    assert virtual_field["citations"] == ["[D240:p15]"]


def test_targeted_schema_mapping_adds_analyst_display_metadata():
    mappings = MappingCoordinator().create_targeted_schema_mappings(
        [
            {
                "id": "napkin_current_expense_per_unit",
                "sheet": "Napkin",
                "value_cell": "C10",
                "label_cell": "B10",
                "data_type": "currency",
                "source_basis": "om_operating_statement",
                "source_period": "current",
                "description": "Current or in-place operating expense per storage unit.",
            }
        ],
        {
            "napkin_current_expense_per_unit": {
                "value": "$1,234",
                "confidence": 0.96,
                "citations": ["[S285:p16]"],
                "reasoning": "Found in EXPENSES section, CURRENT column",
            }
        },
    )

    assert mappings[0]["display_label"] == "Current Expense Per Unit"
    assert mappings[0]["display_context"] == "Napkin · Operating Statement · Expenses · Current"
    assert mappings[0]["source_note"] == "Operating statement · Expenses section · Current period · Page 16"


def test_targeted_table_mapping_adds_analyst_display_metadata():
    mappings = MappingCoordinator().create_targeted_schema_table_mappings(
        [
            {
                "id": "actuals_unit_mix_storage_unit_mix",
                "sheet": "Actuals&UnitMix",
                "description": "Storage unit mix",
                "data_start_row": 5,
                "data_end_row": 10,
                "row_identifier_column": "G",
                "columns": [
                    {"excel_column": "G", "header": "Unit Type", "data_type": "text"},
                    {"excel_column": "K", "header": "Current Rent Average", "data_type": "currency"},
                ],
            }
        ],
        {
            "actuals_unit_mix_storage_unit_mix": {
                "rows": [
                    {
                        "row_index": 0,
                        "row_label": "5 x 10",
                        "values": {"K": "$75"},
                        "confidence": 0.95,
                        "citations": ["[S240:p15]"],
                        "reasoning": "Found in Unit Mix table",
                    }
                ]
            }
        },
    )

    assert mappings[0]["display_label"] == "Current Rent Average · 5 x 10"
    assert mappings[0]["display_context"] == "Actuals & Unit Mix · Storage unit mix"
    assert mappings[0]["source_note"] == "Storage unit mix · Page 15"


def test_targeted_virtual_field_carries_display_metadata():
    virtual_field = _build_targeted_virtual_pdf_field(
        {
            "pdf_field_id": "targeted_napkin_current_expense_per_unit",
            "pdf_field_name": "napkin_current_expense_per_unit",
            "data_type": "currency",
            "extracted_value": "$1,234",
            "confidence": 0.96,
            "citations": ["[S285:p16]"],
            "display_label": "Current Expense Per Unit",
            "display_context": "Napkin · Operating Statement · Expenses · Current",
            "source_note": "Operating statement · Expenses section · Current period · Page 16",
        },
        {"citations": []},
    )

    assert virtual_field["display_label"] == "Current Expense Per Unit"
    assert virtual_field["display_context"] == "Napkin · Operating Statement · Expenses · Current"
    assert virtual_field["source_note"] == "Operating statement · Expenses section · Current period · Page 16"
