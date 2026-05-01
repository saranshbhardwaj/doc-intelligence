"""Helpers for preserving non-calculation evidence in underwriting result artifacts."""

from __future__ import annotations


PRESERVED_RESULT_ARTIFACT_KEYS = (
    "om_data",
    "rent_roll_data",
    "t12_data",
    "market_data",
    "demographics",
    "rent_comps",
    "discrepancies",
    "stress_tests",
    "plausibility_flags",
    "noi_bridge",
)


def get_preserved_unit_mix(existing_artifact: dict | None) -> list[dict]:
    """Return the best preserved unit mix from an existing result artifact."""
    if not isinstance(existing_artifact, dict):
        return []

    candidates = [
        ((existing_artifact.get("rent_roll_data") or {}).get("unit_mix")),
        existing_artifact.get("unit_mix"),
        ((existing_artifact.get("om_data") or {}).get("unit_mix")),
    ]
    for candidate in candidates:
        if isinstance(candidate, list) and candidate:
            return candidate
    return []


def merge_preserved_result_artifact(existing_artifact: dict | None, recalculated_artifact: dict) -> dict:
    """Keep evidence and enrichment blocks when recalculating from edited inputs."""
    if not isinstance(existing_artifact, dict):
        return recalculated_artifact

    merged_artifact = dict(recalculated_artifact)
    for key in PRESERVED_RESULT_ARTIFACT_KEYS:
        if key in existing_artifact and key not in merged_artifact:
            merged_artifact[key] = existing_artifact[key]
    return merged_artifact
