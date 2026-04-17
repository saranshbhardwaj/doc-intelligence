"""Template fill analytics aggregation logic."""


def aggregate_field_stats(all_extracted_data: list[dict]) -> dict:
    """
    Aggregate per-field correction stats from a list of extracted_data dicts.

    Each dict is one fill run's extracted_data (flat or nested llm_extracted format).
    Returns: {field_id: {field_id, total_runs, llm_success, llm_corrected,
                          blank_filled_from_pdf, blank_filled_manually}}
    """
    stats: dict[str, dict] = {}

    for extracted in all_extracted_data:
        if not isinstance(extracted, dict):
            continue
        # Support both flat {field_id: ...} and nested {llm_extracted: {field_id: ...}}
        fields = extracted.get("llm_extracted", extracted)
        # Exclude the manual_edits key if present in flat format
        if "manual_edits" in fields:
            fields = {k: v for k, v in fields.items() if k != "manual_edits"}

        for field_id, data in fields.items():
            if not isinstance(data, dict):
                continue
            s = stats.setdefault(field_id, {
                "field_id": field_id,
                "total_runs": 0,
                "llm_success": 0,
                "llm_corrected": 0,
                "blank_filled_from_pdf": 0,
                "blank_filled_manually": 0,
            })
            s["total_runs"] += 1

            user_edited = data.get("user_edited", False)
            if not user_edited:
                s["llm_success"] += 1
            elif "original_value" in data:
                if data["original_value"] is not None:
                    s["llm_corrected"] += 1
                elif data.get("source") == "pdf_paste":
                    s["blank_filled_from_pdf"] += 1
                else:
                    s["blank_filled_manually"] += 1
            # else: legacy edit (no original_value key) — counted in total_runs only

    return stats
