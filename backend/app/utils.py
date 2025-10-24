# main.py (add near other helpers)
from typing import Any, Dict, List, Union

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

def _merge_projection_years(financials: Dict[str, Any]) -> None:
    """
    If financials has 'projections' mapping years->objects, attempt to
    merge `revenue`, `ebitda`, `net_income` into revenue_by_year/ebitda_by_year/net_income_by_year
    without overwriting explicit entries.
    """
    projections = financials.get("projections")
    if not isinstance(projections, dict):
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

    # key_risks: turn `risk` lists into array of dicts if needed
    kr = data.get("key_risks")
    if isinstance(kr, list):
        normalized_kr = []
        for item in kr:
            if isinstance(item, str):
                normalized_kr.append({"risk": item})
            elif isinstance(item, dict):
                # coerce description lists to strings
                if "description" in item and isinstance(item["description"], (list, tuple)):
                    item["description"] = _coerce_to_str(item["description"])
                normalized_kr.append(item)
            else:
                normalized_kr.append({"risk": str(item)})
        data["key_risks"] = normalized_kr

    # management_team: ensure list of dicts and coerce names
    mg = data.get("management_team")
    if isinstance(mg, list):
        normalized_mg = []
        for m in mg:
            if isinstance(m, str):
                normalized_mg.append({"name": m})
            elif isinstance(m, dict):
                # coerce linkedin or background lists
                if "background" in m and isinstance(m["background"], (list, tuple)):
                    m["background"] = _coerce_to_str(m["background"])
                normalized_mg.append(m)
            else:
                normalized_mg.append({"name": str(m)})
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
