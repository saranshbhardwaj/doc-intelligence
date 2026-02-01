"""Workflow output normalization - makes LLM outputs human-friendly and consistent.

Handles:
- Number formatting with unit detection (millions, thousands, etc.)
- Currency normalization
- Percentage formatting
- Text cleaning and markdown formatting
- Section content validation
- Citation structuring
- Confidence score validation
"""
from typing import Any, Dict, List, Optional
import re
from app.utils.logging import logger

INVESTMENT_MEMO_SECTION_KEYS = [
    "executive_overview",
    "company_overview",
    "market_competition",
    "financial_performance",
    "unit_economics",
    "track_record_value_creation",
    "risks",
    "opportunities",
    "management_culture",
    "esg_snapshot",
    "valuation_scenarios",
    "next_steps",
    "inconsistencies",
]

INVESTMENT_MEMO_SECTION_KEY_ALIASES = {
    "track_record": "track_record_value_creation",
    "esg": "esg_snapshot",
    "valuation": "valuation_scenarios",
}

CITATION_PATTERN = re.compile(r"^\[D\d+:p\d+\]$")


def _normalize_section_key(key: str | None) -> str | None:
    if not key:
        return None
    return INVESTMENT_MEMO_SECTION_KEY_ALIASES.get(key, key)


def _placeholder_section_content(section_key: str) -> str:
    return (
        f"[Content not generated for {section_key.replace('_', ' ').title()} - "
        "section requires additional detail and citations to meet schema requirements.]"
    )


def _clamp_section_content(content: str) -> str:
    if len(content) > 2000:
        return content[:1997] + "..."
    return content


def _filter_citations(citations: Any) -> List[str]:
    if not isinstance(citations, list):
        return []
    filtered: List[str] = []
    for c in citations:
        if not isinstance(c, str):
            c = str(c)
        if CITATION_PATTERN.match(c):
            filtered.append(c)
    return filtered


def _clean_highlights(highlights: Any) -> List[Dict[str, Any]]:
    """Normalize highlights to schema: type, label, value, optional citation/trend/etc."""
    if not isinstance(highlights, list):
        return []

    cleaned: List[Dict[str, Any]] = []
    for item in highlights:
        if not isinstance(item, dict):
            continue

        label = item.get("label")
        value = item.get("value")
        if not label or value is None:
            continue

        highlight_type = item.get("type")
        if highlight_type not in {"company", "metric", "stat"}:
            highlight_type = "stat"

        cleaned_item: Dict[str, Any] = {
            "type": highlight_type,
            "label": str(label),
            "value": value,
        }

        if "formatted" in item and isinstance(item.get("formatted"), str):
            cleaned_item["formatted"] = item["formatted"]
        if "trend" in item and item.get("trend") in {"up", "down", "stable"}:
            cleaned_item["trend"] = item["trend"]
        if "trend_value" in item and isinstance(item.get("trend_value"), str):
            cleaned_item["trend_value"] = item["trend_value"]
        if "detail" in item and isinstance(item.get("detail"), str):
            cleaned_item["detail"] = item["detail"]
        if "year" in item:
            try:
                cleaned_item["year"] = int(item["year"])
            except Exception:
                pass

        citation = item.get("citation")
        if isinstance(citation, str) and CITATION_PATTERN.match(citation):
            cleaned_item["citation"] = citation

        cleaned.append(cleaned_item)

        if len(cleaned) >= 5:
            break

    return cleaned


def _clean_key_metrics(metrics: Any) -> List[Dict[str, Any]]:
    """Normalize key_metrics to schema: label/value required, optional status/year/citation."""
    if not isinstance(metrics, list):
        return []

    cleaned: List[Dict[str, Any]] = []
    for item in metrics:
        if not isinstance(item, dict):
            continue

        label = item.get("label")
        value = item.get("value")
        if not label or value is None:
            continue

        cleaned_item: Dict[str, Any] = {
            "label": str(label),
            "value": str(value) if not isinstance(value, str) else value,
        }

        if "period" in item and isinstance(item.get("period"), str):
            cleaned_item["period"] = item["period"]
        if "status" in item and item.get("status") in {"positive", "negative", "neutral", "strong", "weak", "monitor"}:
            cleaned_item["status"] = item["status"]
        if "year" in item:
            cleaned_item["year"] = item["year"]

        citation = item.get("citation")
        if isinstance(citation, str) and CITATION_PATTERN.match(citation):
            cleaned_item["citation"] = citation

        cleaned.append(cleaned_item)

        if len(cleaned) >= 6:
            break

    return cleaned


def _coerce_investment_memo_sections(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize section keys and enforce schema-required sections/order."""
    keyed: Dict[str, Dict[str, Any]] = {}

    logger.info(f"Coercing sections: received {len(sections)} sections from LLM")

    for section in sections:
        if not isinstance(section, dict):
            logger.warning(f"Skipping non-dict section: {type(section)}")
            continue
        raw_key = section.get("key")
        norm_key = _normalize_section_key(raw_key)
        if not norm_key:
            logger.warning(f"Skipping section with invalid key: {raw_key}")
            continue
        section["key"] = norm_key
        section.setdefault("title", norm_key.replace("_", " ").title())

        content = section.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        if len(content.strip()) < 50:
            logger.debug(f"Section '{norm_key}' has insufficient content (<50 chars), using placeholder")
            content = _placeholder_section_content(norm_key)
        content = _clamp_section_content(content)
        section["content"] = content

        # Normalize citations to schema pattern
        if "citations" in section:
            section["citations"] = _filter_citations(section.get("citations"))

        keyed[norm_key] = section

    present_keys = set(keyed.keys())
    missing_keys = set(INVESTMENT_MEMO_SECTION_KEYS) - present_keys

    logger.info(f"Sections present from LLM: {sorted(present_keys)}")
    if missing_keys:
        logger.warning(f"Missing sections (will add placeholders): {sorted(missing_keys)}")

    ordered_sections: List[Dict[str, Any]] = []
    for key in INVESTMENT_MEMO_SECTION_KEYS:
        if key in keyed:
            ordered_sections.append(keyed[key])
        else:
            ordered_sections.append({
                "key": key,
                "title": key.replace("_", " ").title(),
                "content": _placeholder_section_content(key),
                "citations": []
            })

    logger.info(f"Final sections array: {len(ordered_sections)} sections (required: 12-13)")
    return ordered_sections


def normalize_workflow_output(
    data: Dict[str, Any],
    workflow_name: str,
    currency: str = "USD",
    document_ids: Optional[List[str]] = None,
    db=None,
    raw_text: Optional[str] = None,
    citation_map: Optional[Dict[str, Dict]] = None
) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return data

    normalized = dict(data)

    # ─────────────────────────────────────
    # Citation resolution (KEEP - business logic)
    # ─────────────────────────────────────
    if citation_map and raw_text:
        try:
            citation_pattern = r'\[D\d+:p\d+\]'
            citation_tokens = re.findall(citation_pattern, raw_text)
            unique_tokens = sorted(set(citation_tokens))

            logger.info(f"Citation resolution: {len(unique_tokens)} unique citations found")

            # Override references with ground truth from raw text
            normalized["references"] = unique_tokens

        except Exception as e:
            logger.error(f"Citation resolution failed: {e}", exc_info=True)

    # ─────────────────────────────────────
    # Investment Memo specific normalization
    # ─────────────────────────────────────
    if workflow_name in ["Investment Memo", "Investment Memo Formatter"]:

        # Sections cleanup
        if "sections" in normalized:
            normalized["sections"] = normalize_sections(normalized["sections"])
            normalized["sections"] = _coerce_investment_memo_sections(normalized["sections"])

        # Inject currency into financials block inside sections
        for section in normalized.get("sections", []):
            financials = section.get("financials")
            if isinstance(financials, dict):
                financials.setdefault("currency", normalized.get("currency", currency))
                # Remove financials if historical is empty/missing
                if not financials.get("historical"):
                    section.pop("financials", None)

        # Normalize highlights and key_metrics in sections
        for section in normalized.get("sections", []):
            if "highlights" in section:
                section["highlights"] = _clean_highlights(section["highlights"])
            if "key_metrics" in section:
                section["key_metrics"] = _clean_key_metrics(section["key_metrics"])
            if "citations" in section:
                section["citations"] = _filter_citations(section["citations"])

        # Normalize valuation cases
        if isinstance(normalized.get("valuation"), dict):
            for case_key in ["base_case", "upside_case", "downside_case"]:
                case = normalized["valuation"].get(case_key)
                if not isinstance(case, dict):
                    continue
                # Normalize field names
                if "ev" not in case and "enterprise_value" in case:
                    case["ev"] = case.pop("enterprise_value")
                if "multiple" not in case:
                    for alt in ("ev_ebitda", "asking_ev_ebitda"):
                        if alt in case:
                            case["multiple"] = case.pop(alt)
                            break
                # Drop if missing required fields
                if "ev" not in case or "multiple" not in case:
                    normalized["valuation"].pop(case_key, None)

        # Prune to allowed top-level keys only
        allowed_keys = {
            "currency", "sections", "company_overview", "risks",
            "opportunities", "management", "valuation", "esg",
            "next_steps", "inconsistencies", "references", "meta",
        }
        normalized = {k: v for k, v in normalized.items() if k in allowed_keys}

        # Clamp confidence scores
        normalize_confidence_scores(normalized)

        logger.info("Investment Memo normalization complete", extra={
            "sections_count": len(normalized.get("sections", [])),
            "references_count": len(normalized.get("references", [])),
        })

    return normalized


def normalize_generic_workflow(data: Dict[str, Any]) -> Dict[str, Any]:
    """Generic normalization for any workflow output."""
    normalized = dict(data)

    # Clean null values
    normalized = {k: v for k, v in normalized.items() if v is not None}

    # Validate confidence scores
    normalize_confidence_scores(normalized)

    return normalized


def normalize_sections(sections: Any) -> List[Dict[str, Any]]:
    """Normalize sections array - ensure each section has proper structure.

    Handles:
    - String arrays -> convert to proper objects
    - Empty content -> mark as placeholder
    - Missing fields -> add defaults
    """
    if not sections:
        return []

    if not isinstance(sections, list):
        logger.warning(f"Sections should be a list, got {type(sections)}")
        return []

    normalized_sections = []

    for idx, section in enumerate(sections):
        # Handle string sections (LLM returned just titles)
        if isinstance(section, str):
            logger.warning(f"Section {idx} is a string, converting to object")
            section_key = section.lower().replace(" ", "_").replace("&", "and").replace("/", "_")
            normalized_section = {
                "key": section_key,
                "title": section,
                "content": "[Content not generated]",
                "citations": []
            }
        elif isinstance(section, dict):
            normalized_section = dict(section)

            # Ensure required fields
            if "key" not in normalized_section and "title" in normalized_section:
                normalized_section["key"] = normalized_section["title"].lower().replace(" ", "_").replace("&", "and").replace("/", "_")

            if "title" not in normalized_section:
                normalized_section["title"] = normalized_section.get("key", f"Section {idx + 1}").replace("_", " ").title()

            if "content" not in normalized_section or not normalized_section["content"]:
                normalized_section["content"] = "[Content not generated]"
            else:
                # Clean and format content
                normalized_section["content"] = clean_markdown_content(normalized_section["content"])

            # Ensure citations are strings (don't convert to objects)
            if "citations" not in normalized_section:
                normalized_section["citations"] = []
            elif isinstance(normalized_section["citations"], list):
                # Keep citations as strings - they should be citation tokens like "[D1:p1]"
                # No need to convert to objects or clean them
                normalized_section["citations"] = [
                    c if isinstance(c, str) else str(c)
                    for c in normalized_section["citations"]
                ]
            else:
                normalized_section["citations"] = []
        else:
            logger.warning(f"Unknown section type: {type(section)}")
            continue

        # Remove unexpected keys for schema compliance
        allowed_keys = {
            "key",
            "title",
            "content",
            "citations",
            "confidence",
            "highlights",
            "key_metrics",
            "financials",
        }
        normalized_section = {k: v for k, v in normalized_section.items() if k in allowed_keys}

        normalized_sections.append(normalized_section)

    return normalized_sections


def normalize_company_overview(company: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize company overview section."""
    if not isinstance(company, dict):
        return {}

    normalized = dict(company)

    # Ensure required fields exist
    normalized.setdefault("company_name", "Unknown")
    normalized.setdefault("industry", "")
    normalized.setdefault("business_structure", "")

    # Normalize confidence
    if "confidence" in normalized:
        normalized["confidence"] = normalize_confidence(normalized["confidence"])

    return normalized


def normalize_market_analysis(market: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize market analysis section."""
    if not isinstance(market, dict):
        return {}

    normalized = dict(market)

    # Normalize confidence
    if "confidence" in normalized:
        normalized["confidence"] = normalize_confidence(normalized["confidence"])

    return normalized


def normalize_financials(financials: Dict[str, Any], currency: str) -> Dict[str, Any]:
    """Normalize financial data and format numbers."""
    if not isinstance(financials, dict):
        return {}

    normalized = dict(financials)
    normalized.setdefault("currency", currency)

    # Normalize historicals
    if "historical" in normalized and isinstance(normalized["historical"], list):
        for entry in normalized["historical"]:
            if not isinstance(entry, dict):
                continue
            # Format numeric fields
            for key in ["revenue", "ebitda", "margin", "growth"]:
                if key in entry:
                    entry[key] = normalize_number(entry[key])

    # Normalize metrics
    if "metrics" in normalized and isinstance(normalized["metrics"], dict):
        for key, value in normalized["metrics"].items():
            if key != "citation":  # Don't normalize citations
                normalized["metrics"][key] = normalize_number(value)

    return normalized


def normalize_valuation_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize valuation case data."""
    if not isinstance(case, dict):
        return {}

    normalized = dict(case)

    # Format numeric fields
    for key in ["enterprise_value", "ev_ebitda", "irr", "moic"]:
        if key in normalized:
            normalized[key] = normalize_number(normalized[key])

    return normalized


def normalize_risk_items(risks: Any) -> List[Dict[str, Any]]:
    """Normalize risk items to ensure proper structure.

    Handles:
    - Missing category
    - Wrong field names ("risk" instead of "description")
    - Extra fields (inferred/confidence)
    """
    if not risks:
        return []

    if not isinstance(risks, list):
        logger.warning(f"Risks should be a list, got {type(risks)}")
        return []

    normalized_risks = []

    for risk in risks:
        if not isinstance(risk, dict):
            continue

        normalized = {}

        # Handle wrong field name "risk"
        if "description" in risk:
            normalized["description"] = risk["description"]
        elif "risk" in risk:
            normalized["description"] = risk["risk"]
        else:
            normalized["description"] = "Unspecified risk"

        # Ensure category exists
        normalized["category"] = risk.get("category", "General")

        # Include severity if present, normalize to schema enum
        severity = risk.get("severity", "Medium")
        if isinstance(severity, str):
            severity = severity.strip().capitalize()
        if severity not in {"Low", "Medium", "High", "Critical"}:
            severity = "Medium"
        normalized["severity"] = severity

        # Include citations if present
        if "citations" in risk:
            normalized["citations"] = risk["citations"]

        normalized_risks.append(normalized)

    return normalized_risks


def normalize_opportunity_items(opps: Any) -> List[Dict[str, Any]]:
    """Normalize opportunity items to ensure proper structure."""
    if not opps:
        return []

    if not isinstance(opps, list):
        logger.warning(f"Opportunities should be a list, got {type(opps)}")
        return []

    normalized_opps = []

    for opp in opps:
        if not isinstance(opp, dict):
            continue

        normalized = {}

        # Ensure required fields
        normalized["description"] = opp.get("description", "Unspecified opportunity")
        normalized["category"] = opp.get("category", "General")
        impact = opp.get("impact", "Medium")
        if isinstance(impact, str):
            impact = impact.strip().capitalize()
        if impact not in {"Low", "Medium", "High"}:
            impact = "Medium"
        normalized["impact"] = impact

        # Include citations if present
        if "citations" in opp:
            normalized["citations"] = opp["citations"]

        normalized_opps.append(normalized)

    return normalized_opps


def normalize_confidence_scores(data: Any) -> None:
    """Normalize all confidence scores in data to 0-1 range."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "confidence":
                data[key] = normalize_confidence(value)
            else:
                normalize_confidence_scores(value)
    elif isinstance(data, list):
        for item in data:
            normalize_confidence_scores(item)


def normalize_confidence(value: Any) -> float:
    """Normalize confidence value to 0-1 range."""
    try:
        if isinstance(value, str):
            value = float(value)
        if value > 1:
            value = value / 100
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.5


def normalize_number(value: Any) -> Any:
    """Normalize numeric values and handle strings like '1.7% CAGR'."""
    if value is None:
        return None

    # If it's already a number, return as-is
    if isinstance(value, (int, float)):
        return value

    # Handle string values
    if isinstance(value, str):
        # Extract numeric part from strings like "1.7% CAGR"
        match = re.search(r'[-+]?[0-9]*\.?[0-9]+', value)
        if match:
            num = float(match.group())
            # If percentage, convert to decimal
            if '%' in value:
                return num / 100
            return num

    return value


def clean_markdown_content(content: str) -> str:
    """Clean and format markdown content.

    - Remove duplicate headers
    - Clean up spacing
    """
    if not isinstance(content, str):
        return ""

    # Remove duplicate headers (e.g., "## Section\n## Section")
    lines = content.split('\n')
    cleaned_lines = []
    prev_line = None

    for line in lines:
        line = line.strip()
        if line and line == prev_line:
            continue
        cleaned_lines.append(line)
        prev_line = line

    # Remove excess blank lines
    cleaned_content = '\n'.join(cleaned_lines)
    cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)

    return cleaned_content.strip()
