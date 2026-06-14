import json
from pathlib import Path


FIXTURE_PATH = (
    Path(__file__).resolve().parents[5]
    / "evals"
    / "datasets"
    / "golden"
    / "rag-chat-96"
    / "rag_retrieval_dedup.jsonl"
)


def _load_rows():
    return [
        json.loads(line)
        for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_rag_chat_96_retrieval_fixture_uses_gold_aware_assertions():
    rows = _load_rows()

    for row in rows:
        retrieval_assertion = next(
            assertion
            for assertion in row["assert"]
            if assertion.get("metric") == "retrieval/page_recall_80"
        )
        value = retrieval_assertion["value"]

        assert "benchmark_gold_evidence" in value
        assert "benchmarkGoldUsable" in value
        assert "expected_anchors || context.vars.expected_pages" in value


def test_rag_chat_96_retrieval_fixture_keeps_gold_ids_in_scope():
    rows = _load_rows()
    mismatches = []

    for row in rows:
        vars_ = row["vars"]
        question_id = vars_.get("benchmark_question_id")
        document_ids = set(json.loads(vars_["document_ids"]))
        benchmark_gold = json.loads(vars_["benchmark_gold_evidence"])
        benchmark_target_ids = set(json.loads(vars_["benchmark_target_document_ids"]))
        metadata = row.get("_metadata", {}).get("benchmark_annotation", {})
        metadata_target_ids = set(metadata.get("target_document_ids") or [])
        metadata_gold_ids = {
            item["document_id"]
            for item in metadata.get("gold_evidence") or []
            if isinstance(item, dict) and item.get("document_id")
        }
        benchmark_gold_ids = {
            item["document_id"]
            for item in benchmark_gold
            if isinstance(item, dict) and item.get("document_id")
        }

        problems = []
        if not benchmark_target_ids <= document_ids:
            problems.append(f"target ids out of scope: {sorted(benchmark_target_ids - document_ids)}")
        if not benchmark_gold_ids <= document_ids:
            problems.append(f"gold ids out of scope: {sorted(benchmark_gold_ids - document_ids)}")
        if metadata_target_ids != benchmark_target_ids:
            problems.append(
                f"metadata target ids {sorted(metadata_target_ids)} != vars target ids {sorted(benchmark_target_ids)}"
            )
        if metadata_gold_ids != benchmark_gold_ids:
            problems.append(
                f"metadata gold ids {sorted(metadata_gold_ids)} != vars gold ids {sorted(benchmark_gold_ids)}"
            )

        if problems:
            mismatches.append(f"{question_id}: {'; '.join(problems)}")

    assert not mismatches, "\n".join(mismatches)


def test_point_blank_property_tax_gold_evidence_stays_in_scope():
    rows = _load_rows()
    row = next(
        candidate
        for candidate in rows
        if candidate["vars"].get("benchmark_question_id") == "pb-tax-2024"
    )

    document_ids = set(json.loads(row["vars"]["document_ids"]))
    benchmark_gold = json.loads(row["vars"]["benchmark_gold_evidence"])
    benchmark_target_ids = set(json.loads(row["vars"]["benchmark_target_document_ids"]))

    assert benchmark_target_ids <= document_ids
    assert {item["document_id"] for item in benchmark_gold} <= document_ids
    assert row["_metadata"]["benchmark_annotation"]["target_document_ids"] == [
        "54225e7e-dc4d-4ad3-9c4a-9f021798edfc"
    ]


def test_tulsa_unit_mix_parking_uses_expected_anchor_fallback():
    rows = _load_rows()
    row = next(
        candidate
        for candidate in rows
        if candidate["vars"].get("benchmark_question_id") == "tulsa-unit-mix-parking"
    )

    assert json.loads(row["vars"]["benchmark_gold_evidence"]) == []
    assert row["_metadata"]["benchmark_annotation"]["gold_evidence"] == []