# app/utils/normalization.py
from typing import Any, Dict, Union, Optional
import re

def _normalize_llm_output(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize LLM response keys to canonical names expected by our Pydantic models and frontend.
    Accepts either:
      - raw = { "company_information": {...}, ... }  OR
      - raw = { "data": { ... }, "metadata": {...} }
    Returns: normalized dict shaped { "data": {...}, "metadata": {...} } (metadata may be preserved)
    """
    result: Dict[str, Any] = {}
    data = None
    metadata = None

    if not isinstance(raw, dict):
        return {"data": raw, "metadata": None}

    if "data" in raw and isinstance(raw["data"], dict):
        data = dict(raw["data"])  # copy
        metadata = raw.get("metadata")
    else:
        # assume raw itself is the extracted data
        data = dict(raw)

    # canonicalize company_info
    ci = data.get("company_information") or {}
    if not isinstance(ci, dict):
        ci = {}
    # map common synonyms from your cached example -> canonical fields
    syn_map_company = {
        "sic_code": "sic_codes",
        "sic_codes": "sic_codes",
        "naics_code": "naics_codes",
        "naics_codes": "naics_codes",
        "location": "headquarters",
        "company_structure": "business_structure",
        "state_of_incorporation": "state_of_incorporation",  # keep if present
        "company_id": "company_id",
        "company_name": "company_name",
        "website": "website",
    }
    canonical_ci = {}
    for k, v in ci.items():
        # normalize keys that are in map
        target = syn_map_company.get(k, k)
        canonical_ci[target] = v

    # Ensure pre-existing fields in company_information appear even if missing
    # (Pydantic will apply defaults)
    data["company_info"] = canonical_ci

    # canonicalize transaction details (join lists, map synonyms)
    td = data.get("transaction_details") or {}
    if not isinstance(td, dict):
        td = {}
    syn_map_td = {
        "seller_motivation": "seller_motivation",
        "seller_post_sale_involvement": "post_sale_involvement",
        "seller_post_sale_involvement": "post_sale_involvement",
        "seller_post_sale_involvement_notes": "post_sale_involvement",
        "seller_post_sale_involvement_details": "post_sale_involvement",
        "seller_post_sale_involvement": "post_sale_involvement",
        "seller_post_sale": "post_sale_involvement",
        "auction_deadline": "auction_deadline",
        "auction_process": "auction_process",
        "auction": "auction_process",
        "asking_price": "asking_price",
        "assets_available_for_acquisition": "assets_available_for_acquisition",
    }
    canonical_td = {}
    for k, v in td.items():
        target = syn_map_td.get(k, k)
        # textual fields -> coerce to str
        if isinstance(v, (list, tuple)):
            canonical_td[target] = _coerce_to_str(v)
        else:
            canonical_td[target] = v

    data["transaction_details"] = canonical_td

    # Normalize textual single-fields in top-level like investment_thesis etc.
    for text_key in ("investment_thesis", "extraction_notes"):
        if text_key in data:
            data[text_key] = _coerce_to_str(data[text_key])

    # Financials: try to merge projections into year maps
    fin = data.get("financial_performance")
    if isinstance(fin, dict):
        _merge_projection_years(fin)
        # coerce some fields to numeric where possible? (leave this to further steps)
        data["financials"] = fin

    # Apply all type coercion and cleaning before Pydantic validation
    _apply_type_coercions(data)

    # Clean null values from ALL Dict[str, float] fields across the response
    # This prevents Pydantic validation errors when Claude returns null for missing data
    _clean_all_dict_nulls(data)

    # key_risks: turn `risk` lists into array of dicts if needed
    # REQUIRED FIELD: "risk" - must be present and non-empty
    kr = data.get("key_risks")
    if isinstance(kr, list):
        normalized_kr = []
        for item in kr:
            if isinstance(item, str):
                # String -> wrap in dict with "risk" key
                if item.strip():  # Only add non-empty strings
                    normalized_kr.append({"risk": item.strip()})
            elif isinstance(item, dict):
                # Dict -> ensure "risk" field exists and is non-empty
                if "risk" not in item or not item["risk"]:
                    # Try to infer from description or severity
                    if "description" in item and item["description"]:
                        item["risk"] = item["description"][:50] + "..." if len(str(item["description"])) > 50 else str(item["description"])
                    elif "severity" in item:
                        item["risk"] = f"{item['severity']} severity risk"
                    else:
                        # Skip invalid entries
                        continue

                # Clean empty strings to None
                if item.get("risk") == "":
                    continue  # Skip entries with empty risk

                # Coerce description lists to strings
                if "description" in item and isinstance(item["description"], (list, tuple)):
                    item["description"] = _coerce_to_str(item["description"])

                normalized_kr.append(item)
            else:
                # Other types -> convert to string
                if str(item).strip():
                    normalized_kr.append({"risk": str(item).strip()})
        data["key_risks"] = normalized_kr

    # management_team: ensure list of dicts and coerce names
    # REQUIRED FIELD: "name" - must be present and non-empty
    mg = data.get("management_team")
    if isinstance(mg, list):
        normalized_mg = []
        for m in mg:
            if isinstance(m, str):
                # String -> wrap in dict with "name" key
                if m.strip():  # Only add non-empty strings
                    normalized_mg.append({"name": m.strip()})
            elif isinstance(m, dict):
                # Dict -> ensure "name" field exists and is non-empty
                if "name" not in m or not m["name"]:
                    # Try to infer from title or skip
                    if "title" in m and m["title"]:
                        m["name"] = f"[{m['title']}]"  # Placeholder name from title
                    else:
                        # Skip invalid entries
                        continue

                # Clean empty strings to None
                if m.get("name") == "":
                    continue  # Skip entries with empty name

                # Coerce linkedin or background lists
                if "background" in m and isinstance(m["background"], (list, tuple)):
                    m["background"] = _coerce_to_str(m["background"])

                normalized_mg.append(m)
            else:
                # Other types -> convert to string
                if str(m).strip():
                    normalized_mg.append({"name": str(m).strip()})
        data["management_team"] = normalized_mg

    # raw_sections: if provided as strings or lists, keep
    rs = data.get("raw_sections")
    if isinstance(rs, dict):
        # ensure each entry has text string
        for k, v in rs.items():
            if isinstance(v, dict) and "text" in v:
                v["text"] = _coerce_to_str(v["text"])
            elif isinstance(v, (list, tuple)):
                # try join
                rs[k] = {"text": _coerce_to_str(v)}
            else:
                rs[k] = {"text": _coerce_to_str(v)}
        data["raw_sections"] = rs

    # field_confidence / field_provenance left as-is (they're useful)
    # derived_metrics, growth_analysis also left as-is

    result["data"] = data
    if metadata is not None:
        result["metadata"] = metadata

    return result

def _coerce_to_str(value: Any) -> Union[str, None]:
    """Convert lists to joined string, keep strings, None stays None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        # Filter Nones, join with " ; "
        cleaned = [str(v).strip() for v in value if v is not None]
        return " ; ".join(cleaned) if cleaned else None
    # fallback
    return str(value)

def _clean_null_values(data_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Remove null/None values from dictionary (Pydantic doesn't accept nulls in Dict[str, float])"""
    if not isinstance(data_dict, dict):
        return data_dict
    return {k: v for k, v in data_dict.items() if v is not None}

def _clean_all_dict_nulls(data: Dict[str, Any]) -> None:
    """
    Recursively clean null values from all Dict[str, float] fields in the data structure.
    This prevents Pydantic validation errors when Claude returns null for missing data points.

    Cleans these fields:
    - financials: revenue_by_year, ebitda_by_year, adjusted_ebitda_by_year, net_income_by_year, gross_margin_by_year
    - customers: revenue_mix_by_segment
    - operating_metrics: capex_by_year, fcf_by_year
    - extracted_data: field_confidence
    """
    # Clean financials section
    if "financials" in data and isinstance(data["financials"], dict):
        fin = data["financials"]
        for field in ["revenue_by_year", "ebitda_by_year", "adjusted_ebitda_by_year",
                      "net_income_by_year", "gross_margin_by_year"]:
            if field in fin and isinstance(fin[field], dict):
                fin[field] = _clean_null_values(fin[field])

    # Clean customers section
    if "customers" in data and isinstance(data["customers"], dict):
        customers = data["customers"]
        if "revenue_mix_by_segment" in customers and isinstance(customers["revenue_mix_by_segment"], dict):
            customers["revenue_mix_by_segment"] = _clean_null_values(customers["revenue_mix_by_segment"])

    # Clean operating_metrics section
    if "operating_metrics" in data and isinstance(data["operating_metrics"], dict):
        om = data["operating_metrics"]
        for field in ["capex_by_year", "fcf_by_year"]:
            if field in om and isinstance(om[field], dict):
                om[field] = _clean_null_values(om[field])

    # Clean field_confidence at top level
    if "field_confidence" in data and isinstance(data["field_confidence"], dict):
        data["field_confidence"] = _clean_null_values(data["field_confidence"])

def _merge_projection_years(financials: Dict[str, Any]) -> None:
    """
    If financials has 'projections' mapping years->objects, attempt to
    merge `revenue`, `ebitda`, `net_income` into revenue_by_year/ebitda_by_year/net_income_by_year
    without overwriting explicit entries.
    Also filters out null values from all financial year dictionaries.
    """
    projections = financials.get("projections")
    if not isinstance(projections, dict):
        # Still need to clean existing dictionaries
        for key in ["revenue_by_year", "ebitda_by_year", "net_income_by_year",
                    "adjusted_ebitda_by_year", "gross_margin_by_year", "capex_by_year", "fcf_by_year"]:
            if key in financials and isinstance(financials[key], dict):
                financials[key] = _clean_null_values(financials[key])
        return

    # Ensure year maps exist
    revenue_map = financials.setdefault("revenue_by_year", {})
    ebitda_map = financials.setdefault("ebitda_by_year", {})
    net_map = financials.setdefault("net_income_by_year", {})

    for year_key, metrics in projections.items():
        if not isinstance(metrics, dict):
            continue
        # prefer existing explicit entries; only set if key missing
        if "revenue" in metrics and year_key not in revenue_map:
            try:
                revenue_map[year_key] = float(metrics["revenue"])
            except Exception:
                # leave as-is if not parseable
                revenue_map.setdefault(year_key, None)
        if "ebitda" in metrics and year_key not in ebitda_map:
            try:
                ebitda_map[year_key] = float(metrics["ebitda"])
            except Exception:
                ebitda_map.setdefault(year_key, None)
        if "net_income" in metrics and year_key not in net_map:
            try:
                net_map[year_key] = float(metrics["net_income"])
            except Exception:
                net_map.setdefault(year_key, None)

    # Clean all null values from financial dictionaries
    financials["revenue_by_year"] = _clean_null_values(revenue_map)
    financials["ebitda_by_year"] = _clean_null_values(ebitda_map)
    financials["net_income_by_year"] = _clean_null_values(net_map)

    # Clean other financial year dictionaries if present
    for key in ["adjusted_ebitda_by_year", "gross_margin_by_year", "capex_by_year", "fcf_by_year"]:
        if key in financials and isinstance(financials[key], dict):
            financials[key] = _clean_null_values(financials[key])


# ==================== TYPE COERCION FUNCTIONS ====================
# These functions handle converting LLM outputs to proper Python types
# to prevent Pydantic validation errors.
#
# ARCHITECTURE:
# 1. _apply_type_coercions() - Main orchestrator, applies coercions to all sections
# 2. _coerce_to_int() - Handles string integers, ranges, approximations
# 3. _coerce_to_float() - Handles units (M, K, B), multipliers (x), percentages
# 4. _coerce_to_percentage_decimal() - Converts percentages to 0-1 decimals
# 5. _coerce_to_list() - Converts comma-separated strings to lists
#
# COMMON ISSUES FIXED:
# - Strings instead of numbers: "2005" -> 2005
# - Numbers with units: "15.2M" -> 15200000.0
# - Percentages: "15%" -> 0.15 (for decimal fields) or 15.0 (for float fields)
# - Ranges: "500-1000" -> 750 (midpoint)
# - Comma-separated strings: "A, B, C" -> ["A", "B", "C"]
# - Empty strings: "" -> None
# - Missing required fields in nested objects: Skip or infer from other fields
#
# This layer sits between Claude's raw output and Pydantic validation,
# ensuring data conforms to strict type definitions in models.py

def _apply_type_coercions(data: Dict[str, Any]) -> None:
    """
    Apply all type coercions to the data structure.
    This fixes common issues where Claude returns wrong types:
    - Strings instead of integers: "2005" -> 2005
    - Strings with units instead of floats: "15.2M" -> 15.2
    - Percentages as strings: "15%" -> 15.0 or 0.15
    - Comma-separated strings instead of lists: "A, B, C" -> ["A", "B", "C"]
    - Empty strings instead of None: "" -> None
    """
    # Company Info
    if "company_info" in data and isinstance(data["company_info"], dict):
        ci = data["company_info"]
        ci["founded_year"] = _coerce_to_int(ci.get("founded_year"))
        ci["employees"] = _coerce_to_int(ci.get("employees"))
        # Clean empty strings
        for key in ci:
            if ci[key] == "":
                ci[key] = None

    # Balance Sheet
    if "balance_sheet" in data and isinstance(data["balance_sheet"], dict):
        bs = data["balance_sheet"]
        bs["most_recent_year"] = _coerce_to_int(bs.get("most_recent_year"))
        # Coerce all float fields
        for field in ["total_assets", "current_assets", "fixed_assets", "total_liabilities",
                      "current_liabilities", "long_term_debt", "stockholders_equity", "working_capital"]:
            if field in bs:
                bs[field] = _coerce_to_float(bs[field])

    # Financial Ratios
    if "financial_ratios" in data and isinstance(data["financial_ratios"], dict):
        fr = data["financial_ratios"]
        for field in ["current_ratio", "quick_ratio", "debt_to_equity", "return_on_assets",
                      "return_on_equity", "inventory_turnover", "accounts_receivable_turnover",
                      "ebitda_margin", "capex_pct_revenue", "net_debt_to_ebitda"]:
            if field in fr:
                fr[field] = _coerce_to_float(fr[field])

    # Customer Info
    if "customers" in data and isinstance(data["customers"], dict):
        cust = data["customers"]
        cust["total_count"] = _coerce_to_int(cust.get("total_count"))
        cust["top_customer_concentration_pct"] = _coerce_to_float(cust.get("top_customer_concentration_pct"))
        cust["recurring_revenue_pct"] = _coerce_to_float(cust.get("recurring_revenue_pct"))
        # Handle notable_customers: might be comma-separated string
        if "notable_customers" in cust:
            cust["notable_customers"] = _coerce_to_list(cust["notable_customers"])

    # Market Info
    if "market" in data and isinstance(data["market"], dict):
        mkt = data["market"]
        mkt["market_size_estimate"] = _coerce_to_float(mkt.get("market_size_estimate"))

    # Growth Analysis
    if "growth_analysis" in data and isinstance(data["growth_analysis"], dict):
        ga = data["growth_analysis"]
        # These are decimal percentages (0.15 = 15%)
        ga["historical_cagr"] = _coerce_to_percentage_decimal(ga.get("historical_cagr"))
        ga["projected_cagr"] = _coerce_to_percentage_decimal(ga.get("projected_cagr"))
        ga["organic_pct"] = _coerce_to_percentage_decimal(ga.get("organic_pct"))
        ga["m_and_a_pct"] = _coerce_to_percentage_decimal(ga.get("m_and_a_pct"))

    # Valuation Multiples
    if "valuation_multiples" in data and isinstance(data["valuation_multiples"], dict):
        vm = data["valuation_multiples"]
        for field in ["asking_ev_ebitda", "asking_ev_revenue", "asking_price_ebitda", "exit_ev_ebitda_estimate"]:
            if field in vm:
                vm[field] = _coerce_to_float(vm[field])

    # Capital Structure
    if "capital_structure" in data and isinstance(data["capital_structure"], dict):
        cs = data["capital_structure"]
        for field in ["existing_debt", "debt_to_ebitda", "proposed_leverage", "equity_contribution_estimate"]:
            if field in cs:
                cs[field] = _coerce_to_float(cs[field])

    # Transaction Details
    if "transaction_details" in data and isinstance(data["transaction_details"], dict):
        td = data["transaction_details"]
        td["asking_price"] = _coerce_to_float(td.get("asking_price"))

    # Operating Metrics
    if "operating_metrics" in data and isinstance(data["operating_metrics"], dict):
        om = data["operating_metrics"]
        om["working_capital_pct_revenue"] = _coerce_to_float(om.get("working_capital_pct_revenue"))

    # Strategic Rationale
    if "strategic_rationale" in data and isinstance(data["strategic_rationale"], dict):
        sr = data["strategic_rationale"]
        # Handle competitive_advantages: might be comma-separated string or null
        if "competitive_advantages" in sr:
            sr["competitive_advantages"] = _coerce_to_list(sr["competitive_advantages"])


def _coerce_to_int(value: Any) -> Optional[int]:
    """
    Coerce value to integer, handling common LLM output patterns.
    Examples:
      "2005" -> 2005
      "500-1000" -> 750 (midpoint of range)
      "approximately 150" -> 150
      None -> None
    """
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        # Remove common text patterns
        cleaned = value.strip().lower()
        cleaned = cleaned.replace("approximately", "").replace("~", "").strip()

        # Handle ranges like "500-1000" -> take midpoint
        if "-" in cleaned and cleaned.replace("-", "").replace(",", "").replace(".", "").isdigit():
            parts = cleaned.split("-")
            try:
                low = int(parts[0].strip().replace(",", ""))
                high = int(parts[1].strip().replace(",", ""))
                return (low + high) // 2
            except:
                pass

        # Remove commas and try parsing
        cleaned = cleaned.replace(",", "")
        try:
            return int(float(cleaned))
        except:
            pass

    return None


def _coerce_to_float(value: Any) -> Optional[float]:
    """
    Coerce value to float, handling common LLM output patterns.
    Examples:
      "15.2M" -> 15.2 (assumes millions, returns as-is - you can multiply by 1e6 if needed)
      "1.5x" -> 1.5
      "15%" -> 15.0 (NOT 0.15 - use _coerce_to_percentage_decimal for that)
      "~25%" -> 25.0
      None -> None
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().lower()

        # Remove common prefixes/suffixes
        cleaned = cleaned.replace("approximately", "").replace("~", "").strip()
        cleaned = cleaned.replace("$", "").replace(",", "")

        # Handle percentages: "15%" -> 15.0
        if "%" in cleaned:
            cleaned = cleaned.replace("%", "").strip()
            try:
                return float(cleaned)
            except:
                pass

        # Handle multipliers: "1.5x" -> 1.5
        if cleaned.endswith("x"):
            cleaned = cleaned[:-1].strip()
            try:
                return float(cleaned)
            except:
                pass

        # Handle units: "15.2M", "150K", "1.5B"
        # Note: We extract the number but DON'T multiply by the unit
        # Frontend should handle unit display
        multiplier = 1.0
        if cleaned.endswith("k"):
            cleaned = cleaned[:-1].strip()
            multiplier = 1e3
        elif cleaned.endswith("m"):
            cleaned = cleaned[:-1].strip()
            multiplier = 1e6
        elif cleaned.endswith("b"):
            cleaned = cleaned[:-1].strip()
            multiplier = 1e9

        try:
            return float(cleaned) * multiplier
        except:
            pass

    return None


def _coerce_to_percentage_decimal(value: Any) -> Optional[float]:
    """
    Coerce value to decimal percentage (0.15 = 15%).
    Examples:
      "15%" -> 0.15
      15 -> 0.15 (assumes it's a percentage number)
      0.15 -> 0.15 (already decimal)
      "~25%" -> 0.25
    """
    if value is None or value == "":
        return None

    # If already a float between 0-1, assume it's correct
    if isinstance(value, float) and 0 <= value <= 1:
        return value

    # If it's a number > 1, assume it's percentage form
    if isinstance(value, (int, float)) and value > 1:
        return value / 100.0

    if isinstance(value, str):
        cleaned = value.strip().lower()
        cleaned = cleaned.replace("approximately", "").replace("~", "").strip()

        # Remove % sign
        if "%" in cleaned:
            cleaned = cleaned.replace("%", "").strip()
            try:
                return float(cleaned) / 100.0
            except:
                pass

        # Try parsing as float
        try:
            val = float(cleaned)
            # If > 1, assume it's percentage form
            if val > 1:
                return val / 100.0
            return val
        except:
            pass

    return None


def _coerce_to_list(value: Any) -> Optional[list]:
    """
    Coerce value to list, handling common LLM output patterns.
    Examples:
      "Apple, Microsoft, Google" -> ["Apple", "Microsoft", "Google"]
      ["Apple", "Microsoft"] -> ["Apple", "Microsoft"]
      None -> None
      "" -> None
    """
    if value is None or value == "":
        return None

    if isinstance(value, list):
        # Filter out None and empty strings
        return [item for item in value if item is not None and item != ""]

    if isinstance(value, str):
        # Split by commas, semicolons, or newlines
        items = re.split(r'[,;\n]', value)
        cleaned = [item.strip() for item in items if item.strip()]
        return cleaned if cleaned else None

    # Fallback: convert to string and wrap in list
    return [str(value)]
