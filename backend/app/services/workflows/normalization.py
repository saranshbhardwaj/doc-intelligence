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


def normalize_workflow_output(data: Dict[str, Any], workflow_name: str, currency: str = "USD") -> Dict[str, Any]:
    """Main normalization entry point for workflow outputs.

    Args:
        data: Raw LLM output
        workflow_name: Name of workflow for context-specific normalization
        currency: Currency code (USD, EUR, etc.)

    Returns:
        Normalized data ready for frontend display
    """
    if not isinstance(data, dict):
        return data
    
    normalized = dict(data)
    normalized.setdefault("currency", currency)
    
    # Ensure required top-level fields
    normalized.setdefault("meta", {"version": 2})
    normalized.setdefault("references", [])

    # Workflow-specific normalization
    if workflow_name in ["Investment Memo", "Investment Memo Formatter"]:
        # Sections
        if "sections" in normalized:
            normalized["sections"] = normalize_sections(normalized["sections"])
        else:
            normalized["sections"] = []

        # Ensure minimum sections requirement (schema requires minItems: 2)
        if len(normalized["sections"]) < 2:
            logger.warning(f"Investment Memo has {len(normalized['sections'])} sections, padding to meet minimum of 2")
            # If we have 0 sections, add 2 placeholder sections
            # If we have 1 section, add 1 more placeholder
            while len(normalized["sections"]) < 2:
                placeholder_num = len(normalized["sections"]) + 1
                normalized["sections"].append({
                    "key": f"placeholder_section_{placeholder_num}",
                    "title": f"Section {placeholder_num}",
                    "content": "[Content not generated - LLM did not output sufficient sections]",
                    "citations": []
                })

        # Financials
        if "financials" in normalized:
            normalized["financials"] = normalize_financials(normalized["financials"], currency)
        else:
            normalized["financials"] = {}

        # Company overview
        if "company_overview" in normalized:
            normalized["company_overview"] = normalize_company_overview(normalized["company_overview"])

        # Market analysis
        if "market_analysis" in normalized:
            normalized["market_analysis"] = normalize_market_analysis(normalized["market_analysis"])

        # Valuation cases (base/upside/downside)
        for case in ["base_case", "upside_case", "downside_case"]:
            if "valuation" in normalized and case in normalized["valuation"]:
                normalized["valuation"][case] = normalize_valuation_case(normalized["valuation"][case])

        # ESG, risks, opportunities, management, next_steps
        normalized.setdefault("esg", {})

        # Normalize risks and opportunities with proper structure
        if "risks" in normalized:
            normalized["risks"] = normalize_risk_items(normalized["risks"])
        else:
            normalized["risks"] = []

        if "opportunities" in normalized:
            normalized["opportunities"] = normalize_opportunity_items(normalized["opportunities"])
        else:
            normalized["opportunities"] = []

        normalized.setdefault("management", {"citations":[]})
        normalized.setdefault("next_steps", [])
        normalized.setdefault("inconsistencies", [])

        # Normalize confidence in sections to "High/Medium/Low"
        # for section in normalized["sections"]:
        #     section_conf = section.get("confidence")
        #     section["confidence"] = map_confidence_to_band(section_conf)

        # Normalize references: union of all citations in sections
        citations_set = set()
        for section in normalized["sections"]:
            if "citations" in section:
                section_cits = [str(c) for c in section["citations"] if c]
                section["citations"] = section_cits
                citations_set.update(section_cits)
        normalized["references"] = sorted(list(citations_set))
        
        normalize_confidence_scores(normalized)

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

            if "citations" not in normalized_section:
                normalized_section["citations"] = []
            else:
                normalized_section["citations"] = normalize_citations(normalized_section["citations"])
        else:
            logger.warning(f"Unknown section type: {type(section)}")
            continue

        normalized_sections.append(normalized_section)

    return normalized_sections


def normalize_company_overview(company: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize company overview section."""
    normalized = dict(company)

    # Clean text fields
    for field in ["company_name", "company_id", "industry", "secondary_industry", "headquarters", "description"]:
        if field in normalized and normalized[field]:
            normalized[field] = clean_text(normalized[field])

    # Add provenance if missing
    if "provenance" not in normalized:
        normalized["provenance"] = None

    # Validate confidence
    if "confidence" in normalized:
        normalized["confidence"] = validate_confidence(normalized["confidence"])

    return normalized


def normalize_financials(financials: Dict[str, Any], currency: str = "USD") -> Dict[str, Any]:
    """Normalize historical and metrics financials per schema."""
    normalized = dict(financials)
    normalized["currency"] = currency

    # Historical: ensure array of objects
    hist = normalized.get("historical", [])
    if isinstance(hist, dict):
        # Convert dict of years -> object array
        new_hist = []
        for year_str, values in hist.items():
            try:
                year_int = int(year_str)
            except Exception:
                continue
            new_hist.append({"year": year_int, **values})
        hist = new_hist
    elif not isinstance(hist, list):
        hist = []

    # Ensure each historical record matches schema: year + revenue/ebitda/margin + citation
    normalized_hist = []
    for h in hist:
        rec = dict(h)
        rec.setdefault("citation", [])
        # keep numbers as-is, but optionally format for display
        for field in ["revenue", "ebitda", "margin"]:
            if field in rec and isinstance(rec[field], (int, float)):
                rec[field] = rec[field]
        normalized_hist.append(rec)
    normalized["historical"] = normalized_hist

    # Metrics
    metrics = normalized.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    # Ensure citation exists as array
    metrics.setdefault("citation", [])
    normalized["metrics"] = metrics

    return normalized

def normalize_valuation_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize valuation case structure."""
    if not isinstance(case, dict):
        return {}
    case.setdefault("citations", [])
    for field in ["ev", "multiple", "irr"]:
        if field in case and isinstance(case[field], (int, float)):
            case[field] = case[field]
    return case

def map_confidence_to_band(value: Any) -> str:
    """Convert numeric confidence (0-1 or 0-100) to High/Medium/Low."""
    try:
        num = float(value)
        if num > 1:  # assume percentage
            num = num / 100.0
    except (TypeError, ValueError):
        return "Medium"
    if num >= 0.8:
        return "High"
    elif num >= 0.5:
        return "Medium"
    else:
        return "Low"

def normalize_market_analysis(market: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize market analysis section."""
    if not isinstance(market, dict):
        return {}

    normalized = dict(market)

    # Clean text fields
    for field in ["description", "competitive_position", "growth_drivers"]:
        if field in normalized and normalized[field]:
            normalized[field] = clean_text(normalized[field])

    return normalized


def normalize_risk_items(risks: Any) -> List[Dict[str, Any]]:
    """Normalize risk items to match schema requirements.

    Schema requires: {"description": str, "category": str, "severity": enum, "citations"?: array}

    Handles common LLM mistakes:
    - "risk" field → merge into "description"
    - Missing "category" → add default "General"
    - Extra fields ("inferred", "confidence") → remove
    - Invalid severity values → map to valid enum
    """
    if not risks:
        return []

    if not isinstance(risks, list):
        logger.warning(f"Risks should be a list, got {type(risks)}")
        return []

    normalized_risks = []
    valid_severities = ["Low", "Medium", "High", "Critical"]

    for idx, risk in enumerate(risks):
        if not isinstance(risk, dict):
            logger.warning(f"Risk item {idx} is not a dict, skipping")
            continue

        normalized_risk = {}

        # Handle description field (might be in "risk" or "description")
        if "description" in risk:
            normalized_risk["description"] = clean_text(risk["description"])
        elif "risk" in risk:
            # LLM used "risk" instead of "description"
            normalized_risk["description"] = clean_text(risk["risk"])
        else:
            # No description found, use a placeholder
            normalized_risk["description"] = "[Risk description not provided]"

        # Handle category (add default if missing)
        if "category" in risk:
            normalized_risk["category"] = clean_text(risk["category"])
        else:
            normalized_risk["category"] = "General"

        # Handle severity (validate enum)
        if "severity" in risk:
            severity = str(risk["severity"]).strip()
            # Capitalize first letter to match enum
            severity = severity.capitalize()
            if severity in valid_severities:
                normalized_risk["severity"] = severity
            else:
                # Map invalid values
                severity_lower = severity.lower()
                if severity_lower in ["low", "minor"]:
                    normalized_risk["severity"] = "Low"
                elif severity_lower in ["medium", "moderate"]:
                    normalized_risk["severity"] = "Medium"
                elif severity_lower in ["high", "major"]:
                    normalized_risk["severity"] = "High"
                elif severity_lower in ["critical", "severe"]:
                    normalized_risk["severity"] = "Critical"
                else:
                    normalized_risk["severity"] = "Medium"  # default
        else:
            normalized_risk["severity"] = "Medium"  # default

        # Handle citations (optional)
        if "citations" in risk:
            if isinstance(risk["citations"], list):
                normalized_risk["citations"] = [str(c) for c in risk["citations"] if c]
            elif isinstance(risk["citations"], str):
                normalized_risk["citations"] = [risk["citations"]]

        # Only include these 4 fields (description, category, severity, citations)
        # This removes extra fields like "inferred", "confidence", etc.

        normalized_risks.append(normalized_risk)

    return normalized_risks


def normalize_opportunity_items(opportunities: Any) -> List[Dict[str, Any]]:
    """Normalize opportunity items to match schema requirements.

    Schema requires: {"description": str, "category": str, "impact": enum, "citations"?: array}

    Handles common LLM mistakes:
    - "opportunity" field → merge into "description"
    - Missing "category" → add default "General"
    - Extra fields → remove
    - Invalid impact values → map to valid enum
    """
    if not opportunities:
        return []

    if not isinstance(opportunities, list):
        logger.warning(f"Opportunities should be a list, got {type(opportunities)}")
        return []

    normalized_opportunities = []
    valid_impacts = ["Low", "Medium", "High"]

    for idx, opp in enumerate(opportunities):
        if not isinstance(opp, dict):
            logger.warning(f"Opportunity item {idx} is not a dict, skipping")
            continue

        normalized_opp = {}

        # Handle description field (might be in "opportunity" or "description")
        if "description" in opp:
            normalized_opp["description"] = clean_text(opp["description"])
        elif "opportunity" in opp:
            # LLM used "opportunity" instead of "description"
            normalized_opp["description"] = clean_text(opp["opportunity"])
        else:
            # No description found, use a placeholder
            normalized_opp["description"] = "[Opportunity description not provided]"

        # Handle category (add default if missing)
        if "category" in opp:
            normalized_opp["category"] = clean_text(opp["category"])
        else:
            normalized_opp["category"] = "General"

        # Handle impact (validate enum)
        if "impact" in opp:
            impact = str(opp["impact"]).strip()
            # Capitalize first letter to match enum
            impact = impact.capitalize()
            if impact in valid_impacts:
                normalized_opp["impact"] = impact
            else:
                # Map invalid values
                impact_lower = impact.lower()
                if impact_lower in ["low", "minor"]:
                    normalized_opp["impact"] = "Low"
                elif impact_lower in ["medium", "moderate"]:
                    normalized_opp["impact"] = "Medium"
                elif impact_lower in ["high", "major", "significant"]:
                    normalized_opp["impact"] = "High"
                else:
                    normalized_opp["impact"] = "Medium"  # default
        else:
            normalized_opp["impact"] = "Medium"  # default

        # Handle citations (optional)
        if "citations" in opp:
            if isinstance(opp["citations"], list):
                normalized_opp["citations"] = [str(c) for c in opp["citations"] if c]
            elif isinstance(opp["citations"], str):
                normalized_opp["citations"] = [opp["citations"]]

        # Only include these 4 fields (description, category, impact, citations)

        normalized_opportunities.append(normalized_opp)

    return normalized_opportunities


def normalize_citations(citations: Any) -> List[Dict[str, Any]]:
    """Normalize citations to consistent structure.

    Expected structure:
    {
        "id": "[1]",
        "document": "Document name",
        "page": 5,
        "snippet": "Relevant quote..."
    }
    """
    if not citations:
        return []

    if not isinstance(citations, list):
        return []

    normalized_citations = []

    for citation in citations:
        if isinstance(citation, dict):
            normalized_citation = {
                "id": citation.get("id", ""),
                "document": citation.get("document", "Unknown"),
                "page": citation.get("page"),
                "snippet": citation.get("snippet", "")
            }

            # Clean snippet
            if normalized_citation["snippet"]:
                normalized_citation["snippet"] = clean_text(normalized_citation["snippet"])

            normalized_citations.append(normalized_citation)
        elif isinstance(citation, str):
            # Handle simple string citations
            normalized_citations.append({
                "id": f"[{len(normalized_citations) + 1}]",
                "document": "Unknown",
                "page": None,
                "snippet": citation
            })

    return normalized_citations


def normalize_confidence_scores(data: Dict[str, Any]) -> None:
    """Recursively validate and normalize confidence scores (0-1 range).

    Modifies data in-place.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "confidence":
                data[key] = validate_confidence(value)
            elif isinstance(value, dict):
                normalize_confidence_scores(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        normalize_confidence_scores(item)


def validate_confidence(value: Any) -> Optional[float]:
    """Validate confidence score is between 0 and 1."""
    if value is None:
        return None

    try:
        conf = float(value)
        if conf < 0:
            return 0.0
        if conf > 1:
            # Assume it was provided as percentage (0-100)
            return min(conf / 100.0, 1.0)
        return conf
    except (ValueError, TypeError):
        logger.warning(f"Invalid confidence value: {value}")
        return None


def format_number_with_units(value: Any) -> Dict[str, Any]:
    """Format numbers with appropriate units and return structured data.

    Returns:
    {
        "raw": 111900000,
        "formatted": "111.9",
        "unit": "M",
        "display": "$111.9M"  # With default USD symbol
    }
    """
    if value is None:
        return None

    try:
        num = float(value)
    except (ValueError, TypeError):
        return None

    abs_num = abs(num)

    if abs_num >= 1_000_000_000:
        formatted = round(num / 1_000_000_000, 2)
        unit = "B"
    elif abs_num >= 1_000_000:
        formatted = round(num / 1_000_000, 2)
        unit = "M"
    elif abs_num >= 1_000:
        formatted = round(num / 1_000, 2)
        unit = "K"
    else:
        formatted = round(num, 2)
        unit = ""

    return {
        "raw": num,
        "formatted": formatted,
        "unit": unit,
        "display": f"${formatted}{unit}" if unit else f"${formatted}"
    }


def clean_text(text: Any) -> str:
    """Clean and normalize text content."""
    if not text:
        return ""

    if not isinstance(text, str):
        text = str(text)

    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)

    # Remove leading/trailing whitespace
    text = text.strip()

    return text


def clean_markdown_content(content: str) -> str:
    """Clean and format markdown content.

    Ensures:
    - Proper heading levels
    - Clean lists
    - Proper spacing
    """
    if not content:
        return ""

    # Normalize line endings
    content = content.replace('\r\n', '\n')

    # Remove excessive blank lines (more than 2)
    content = re.sub(r'\n{3,}', '\n\n', content)

    # Ensure space after list markers
    content = re.sub(r'^(\s*[-*+]|\d+\.)\s*', r'\1 ', content, flags=re.MULTILINE)

    # Ensure space after heading markers
    content = re.sub(r'^(#{1,6})\s*', r'\1 ', content, flags=re.MULTILINE)

    return content.strip()


__all__ = [
    "normalize_llm_output",
    "normalize_workflow_output",
    "format_number_with_units"
]