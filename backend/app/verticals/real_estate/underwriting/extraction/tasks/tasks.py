"""Celery tasks for RE underwriting extraction pipeline.

Design:
- Payloads through Redis contain IDs only — no document content.
- Each re_extract_per_doc_task fetches its own chunks from DB.
- chord(group(N extract tasks), chain(merge, discrepancy, calculate))
  ensures parallel extraction with sequential post-processing.
- soft_time_limit + acks_late + reject_on_worker_lost give resilience
  against worker crashes.
"""

from __future__ import annotations

from celery import chain, chord, group, shared_task
from celery.exceptions import SoftTimeLimitExceeded
from pydantic import ValidationError

from app.config import settings
from app.database import get_db
from app.repositories.document_repository import DocumentRepository
from app.repositories.re_underwriting_repo import UnderwritingRunRepository
from app.services.job_tracker import JobProgressTracker
from app.services.llm_client import LLMClient
from app.utils.logging import logger

from ..extractor import extract_document
from ..llm_service import REExtractionLLMService
from ..merger import apply_plausibility_guards, merge_extractions
from ..discrepancy import detect_discrepancies_from_results
from ..schemas import ExtractedDocResult
from ...calculator import calculate
from ...noi_bridge import build_noi_bridge
from ...stress_tests import run_stress_tests
from ...rollover import compute_rollover_risk
from ...verdict import evaluate
from ...schemas.self_storage import SelfStorageInputs, UnitMixRow, VerdictWarning


def _weighted_average_unit_mix_rent(unit_mix: list, field_name: str) -> float | None:
    total_units = 0
    weighted_total = 0.0
    for row in unit_mix or []:
        units = row.num_units or 0
        rent = getattr(row, field_name, None)
        if units <= 0 or rent is None:
            continue
        total_units += units
        weighted_total += units * rent
    return (weighted_total / total_units) if total_units > 0 else None


def _select_best_unit_mix(doc_results: list[ExtractedDocResult]) -> list[UnitMixRow]:
    """Select the best available unit-mix evidence for the result artifact.

    Precedence:
    - Rent roll unit mix wins when present because it reflects in-place inventory.
    - OM unit mix is the fallback during early screening when no rent roll mix is available.
    - T-12 is not treated as the source of truth for unit mix.
    """
    for result in doc_results:
        if result.doc_type == "rent_roll" and result.rent_roll and not result.error and result.rent_roll.unit_mix:
            return [UnitMixRow.model_validate(row) for row in result.rent_roll.unit_mix]
    for result in doc_results:
        if result.doc_type == "om" and result.om and not result.error and result.om.unit_mix:
            return [UnitMixRow.model_validate(row) for row in result.om.unit_mix]
    return []


# OM attribute names that differ from their artifact output key
_OM_FIELD_RENAMES: dict[str, str] = {
    "gpr_annual_projected": "gross_potential_rent_annual",
}
# OM attribute name that produces an additional aliased output key
_OM_FIELD_ALIASES: dict[str, str] = {
    "expense_ratio_pro_forma": "opex_pct",
}


def _build_om_source_data(doc_results: list[ExtractedDocResult]) -> dict | None:
    for result in doc_results:
        if result.doc_type != "om" or not result.om or result.error:
            continue
        om = result.om

        # All scalar fields for free — new fields added to OMExtraction appear automatically
        data: dict = om.model_dump(exclude_none=True, exclude={"unit_mix", "rent_comps"})

        # Apply renames (output key differs from OM attribute name)
        for src, dst in _OM_FIELD_RENAMES.items():
            if src in data:
                data[dst] = data.pop(src)

        # Apply aliases (extra output key alongside the original)
        for src, alias in _OM_FIELD_ALIASES.items():
            if src in data:
                data[alias] = data[src]

        # Computed fields
        if om.vacancy_pct_projected is not None:
            data["occupancy_pct"] = 1.0 - om.vacancy_pct_projected

        # Complex types (serialised separately)
        if om.unit_mix:
            data["unit_mix"] = [row.model_dump() for row in om.unit_mix]
        if om.rent_comps:
            data["rent_comps"] = [row.model_dump() for row in om.rent_comps]

        return {k: v for k, v in data.items() if v not in (None, [], {})}
    return None


def _build_rent_roll_source_data(doc_results: list[ExtractedDocResult]) -> dict | None:
    for result in doc_results:
        if result.doc_type != "rent_roll" or not result.rent_roll or result.error:
            continue
        rr = result.rent_roll
        summary = {
            "total_units": rr.num_units_actual,
            "occupancy_pct": rr.physical_occupancy_pct,
        }
        total_sqft = sum(row.total_sqft or 0 for row in rr.unit_mix)
        if total_sqft > 0:
            summary["total_sqft"] = total_sqft
        avg_in_place_rent = rr.avg_in_place_rent_per_unit_monthly
        if avg_in_place_rent is None:
            avg_in_place_rent = _weighted_average_unit_mix_rent(rr.unit_mix, "current_rent")
        if avg_in_place_rent is not None:
            summary["avg_in_place_rent_per_unit_monthly"] = avg_in_place_rent
        avg_market_rent = rr.avg_market_rent_per_unit_monthly
        if avg_market_rent is None:
            avg_market_rent = _weighted_average_unit_mix_rent(rr.unit_mix, "market_rent")
        if avg_market_rent is not None:
            summary["avg_market_rent_per_unit_monthly"] = avg_market_rent
        annual_gpr = sum(
            (row.num_units or 0) * (row.market_rent if row.market_rent is not None else (row.current_rent or 0)) * 12
            for row in rr.unit_mix
            if row.num_units is not None and (row.market_rent is not None or row.current_rent is not None)
        )
        if annual_gpr > 0:
            summary["annual_gross_potential_rent"] = annual_gpr
        data = {"summary": {key: value for key, value in summary.items() if value is not None}}
        if rr.unit_mix:
            data["unit_mix"] = [row.model_dump() for row in rr.unit_mix]
        if rr.lease_records:
            data["leases"] = [record.model_dump() for record in rr.lease_records]
        if result.extraction_metadata.get("spreadsheet_interpretation"):
            data["source_metadata"] = result.extraction_metadata["spreadsheet_interpretation"]
        if result.extraction_metadata.get("review_warnings"):
            data["review_warnings"] = result.extraction_metadata["review_warnings"]
        return data
    return None


def _build_t12_source_data(doc_results: list[ExtractedDocResult]) -> dict | None:
    for result in doc_results:
        if result.doc_type != "t12" or not result.t12 or result.error:
            continue
        t12 = result.t12
        factor = 12.0 / t12.period_months if (t12.period_months and t12.period_months < 12) else 1.0
        total_revenue = ((t12.gpr_annual_actual or 0) + (t12.other_income_annual or 0)) * factor
        total_opex = sum(
            (value or 0) * factor
            for value in [
                t12.property_tax_annual,
                t12.insurance_annual,
                t12.payroll_annual,
                t12.repairs_maintenance_annual,
                t12.utilities_annual,
                t12.marketing_annual,
                t12.other_opex_annual,
            ]
        )
        if t12.mgmt_fee_pct_actual is not None and total_revenue > 0:
            total_opex += total_revenue * t12.mgmt_fee_pct_actual
        summary = {"total_revenue": total_revenue if total_revenue > 0 else None}
        expense_ratio_actual = t12.expense_ratio_actual
        if expense_ratio_actual is None and total_revenue > 0 and total_opex > 0:
            expense_ratio_actual = total_opex / total_revenue
        if expense_ratio_actual is not None:
            summary["opex_ratio"] = expense_ratio_actual
            summary["expense_ratio_actual"] = expense_ratio_actual
        if t12.period_months is not None:
            summary["period_months"] = t12.period_months
            summary["annualized"] = t12.period_months < 12
        if t12.noi_actual is not None:
            summary["noi_actual"] = t12.noi_actual * factor
        if t12.bad_debt_annual is not None:
            summary["bad_debt_annual"] = t12.bad_debt_annual * factor
        if t12.corrections_collections_annual is not None:
            summary["corrections_collections_annual"] = t12.corrections_collections_annual * factor
        missing_expense_fields = [
            label
            for label, value in [
                ("Property tax", t12.property_tax_annual),
                ("Insurance", t12.insurance_annual),
                ("Payroll", t12.payroll_annual),
                ("Repairs & maintenance", t12.repairs_maintenance_annual),
                ("Utilities", t12.utilities_annual),
                ("Marketing", t12.marketing_annual),
                ("Other OpEx", t12.other_opex_annual),
            ]
            if value is None
        ]
        if missing_expense_fields:
            summary["missing_expense_fields"] = missing_expense_fields
        data = {"summary": {key: value for key, value in summary.items() if value is not None}}
        source_metadata = result.extraction_metadata.get("t12_table_totals")
        if source_metadata:
            data["source_metadata"] = source_metadata
        if result.extraction_metadata.get("review_warnings"):
            data["review_warnings"] = result.extraction_metadata["review_warnings"]
        return data
    return None


def _build_discrepancy_warning(discrepancies: list[dict]) -> VerdictWarning | None:
    material = [
        discrepancy for discrepancy in discrepancies or []
        if discrepancy.get("severity") in {"critical", "error", "warning"}
    ]
    if not material:
        return None

    critical_count = sum(1 for discrepancy in material if discrepancy.get("severity") in {"critical", "error"})
    preview = "; ".join((discrepancy.get("note") or discrepancy.get("field") or "source conflict") for discrepancy in material[:2])
    if len(material) > 2:
        preview = f"{preview}; and {len(material) - 2} more"
    return VerdictWarning(
        key="source_discrepancies",
        message=f"Source documents disagree on underwriting inputs: {preview}.",
        severity="critical" if critical_count else "warning",
    )


def _build_plausibility_warning(plausibility_flags: list[dict]) -> VerdictWarning | None:
    if not plausibility_flags:
        return None

    fields = list(dict.fromkeys(flag.get("field") for flag in plausibility_flags if flag.get("field")))
    preview = ", ".join(field.replace("_", " ") for field in fields[:3])
    if len(fields) > 3:
        preview = f"{preview}, and {len(fields) - 3} more"

    return VerdictWarning(
        key="plausibility_flags",
        message=(
            "Some extracted assumptions were ignored as implausible and require analyst review"
            + (f": {preview}." if preview else ".")
        ),
        severity="critical",
    )


def _build_source_artifact_data(doc_results: list[ExtractedDocResult], plausibility_flags: list[dict] | None = None) -> dict:
    artifact_data: dict = {}
    om_data = _build_om_source_data(doc_results)
    rent_roll_data = _build_rent_roll_source_data(doc_results)
    t12_data = _build_t12_source_data(doc_results)

    if om_data:
        artifact_data["om_data"] = om_data
        demographics = {
            "population": om_data.get("population_3mi"),
            "avg_household_income": om_data.get("avg_household_income_3mi"),
            "sqft_per_capita": om_data.get("storage_sqft_per_capita_3mi"),
        }
        demographics = {key: value for key, value in demographics.items() if value is not None}
        if demographics:
            artifact_data["demographics"] = demographics

        market_data = {
            "nearby_storage_count_1mi": om_data.get("nearby_storage_count_1mi"),
            "nearby_storage_count_3mi": om_data.get("nearby_storage_count_3mi"),
            "nearby_storage_count_5mi": om_data.get("nearby_storage_count_5mi"),
            "market_cap_rate_purchase": om_data.get("market_cap_rate_purchase"),
            "market_cap_rate_sale": om_data.get("market_cap_rate_sale"),
        }
        market_data = {key: value for key, value in market_data.items() if value is not None}
        if market_data:
            artifact_data["market_data"] = market_data
        if om_data.get("rent_comps"):
            artifact_data["rent_comps"] = om_data["rent_comps"]
    if rent_roll_data:
        artifact_data["rent_roll_data"] = rent_roll_data
    if t12_data:
        artifact_data["t12_data"] = t12_data
    if plausibility_flags:
        artifact_data["plausibility_flags"] = plausibility_flags

    return artifact_data


def _get_t12_period_months(doc_results: list[ExtractedDocResult]) -> int | None:
    for result in doc_results:
        if result.doc_type == "t12" and result.t12 and not result.error and result.t12.period_months:
            return result.t12.period_months
    return None


def _get_extracted_om_t12(doc_results: list[ExtractedDocResult]):
    om = None
    t12 = None
    for result in doc_results:
        if result.doc_type == "om" and result.om and not result.error:
            om = result.om
        elif result.doc_type == "t12" and result.t12 and not result.error:
            t12 = result.t12
    return om, t12


def _get_db_session():
    return next(get_db())



@shared_task(
    bind=True,
    soft_time_limit=settings.re_uw_task_soft_time_limit_seconds,
    acks_late=True,
    reject_on_worker_lost=True,
)
def re_extract_per_doc_task(self, payload: dict) -> dict:
    """Extract structured data from one document. Fetches own chunks from DB."""
    run_id = payload["run_id"]
    job_id = payload["job_id"]
    doc_type = payload["doc_type"]
    document_id = payload["document_id"]
    source_index = payload.get("source_index", 1)

    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)

    try:
        tracker.update_progress(
            status="extracting",
            current_stage=f"extracting_{doc_type}",
            progress_percent=30,
            message=f"Extracting {doc_type.upper()}...",
        )
        doc_repo = DocumentRepository()
        chunks = doc_repo.get_chunks_for_document(document_id)

        if not chunks:
            logger.warning(f"No chunks found for document {document_id}", extra={"run_id": run_id})
            result = ExtractedDocResult(
                run_id=run_id, job_id=job_id, doc_type=doc_type,
                error=f"No chunks found for document {document_id}",
            )
            return result.model_dump()

        client = LLMClient(
            api_key=settings.anthropic_api_key,
            model=settings.synthesis_llm_model,
            max_tokens=settings.synthesis_llm_max_tokens,
            max_input_chars=settings.llm_max_input_chars,
            timeout_seconds=settings.synthesis_llm_timeout_seconds,
        )
        service = REExtractionLLMService(client, run_id=run_id)
        result = extract_document(run_id, job_id, doc_type, chunks, service, source_index, document_id)
        return result.model_dump()

    except SoftTimeLimitExceeded:
        logger.error(f"Soft time limit exceeded for {doc_type}", extra={"run_id": run_id})
        tracker.mark_error(
            error_stage="extraction",
            error_message=f"Extraction timed out for {doc_type.upper()}",
            internal_error="SoftTimeLimitExceeded",
            error_type="timeout",
            is_retryable=False,
        )
        raise
    except Exception as e:
        logger.error(f"Extraction failed for {doc_type}: {e}", extra={"run_id": run_id})
        if doc_type in ("t12", "rent_roll"):
            logger.warning(f"Optional doc {doc_type} failed — continuing pipeline")
            result = ExtractedDocResult(run_id=run_id, job_id=job_id, doc_type=doc_type, error=str(e)[:500])
            return result.model_dump()
        tracker.mark_error(
            error_stage="extraction",
            error_message="Failed to extract Offering Memorandum",
            internal_error=str(e)[:1000],
            error_type="extraction_error",
            is_retryable=False,
        )
        raise


@shared_task(
    bind=True,
    soft_time_limit=settings.re_uw_task_soft_time_limit_seconds,
    acks_late=True,
    reject_on_worker_lost=True,
)
def re_merge_extractions_task(self, doc_result_dicts: list[dict]) -> dict:
    """Fan-in: merge per-doc extraction results into SelfStorageInputs dict."""
    if not doc_result_dicts:
        raise ValueError("No extraction results to merge")

    run_id = doc_result_dicts[0]["run_id"]
    job_id = doc_result_dicts[0]["job_id"]
    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)

    try:
        tracker.update_progress(
            status="extracting", current_stage="merging",
            progress_percent=60, message="Merging extracted data...",
        )
        results = [ExtractedDocResult(**d) for d in doc_result_dicts]
        sanitized_results, plausibility_flags = apply_plausibility_guards(results)
        if plausibility_flags:
            logger.warning(
                "Plausibility guards ignored extracted underwriting values",
                extra={"run_id": run_id, "flag_count": len(plausibility_flags)},
            )
        merged_inputs, field_citations = merge_extractions(sanitized_results)

        # Merge per-doc citation_context dicts (keys are unique: S{source_index}:p{page})
        merged_citation_context: dict = {}
        for d in doc_result_dicts:
            merged_citation_context.update(d.get("citation_context", {}))

        return {
            "run_id": run_id,
            "job_id": job_id,
            "merged_inputs": merged_inputs,
            "field_citations": field_citations,
            "citation_context": merged_citation_context,
            "doc_results": [result.model_dump() for result in sanitized_results],
            "plausibility_flags": plausibility_flags,
        }
    except SoftTimeLimitExceeded:
        tracker.mark_error(
            error_stage="merging", error_message="Merge timed out",
            internal_error="SoftTimeLimitExceeded", error_type="timeout", is_retryable=False,
        )
        raise
    except Exception as e:
        logger.error(f"Merge failed: {e}", extra={"run_id": run_id})
        tracker.mark_error(
            error_stage="merging", error_message="Failed to merge extracted data",
            internal_error=str(e)[:1000], error_type="merge_error", is_retryable=False,
        )
        raise


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True)
def re_detect_discrepancies_task(self, payload: dict) -> dict:
    """Detect cross-document discrepancies. Non-fatal — logs and continues."""
    run_id = payload["run_id"]
    job_id = payload["job_id"]
    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)

    try:
        tracker.update_progress(
            status="extracting", current_stage="discrepancy_detection",
            progress_percent=70, message="Checking for inconsistencies...",
        )
        results = [ExtractedDocResult(**d) for d in payload.get("doc_results", [])]
        discrepancies = detect_discrepancies_from_results(results, payload.get("merged_inputs", {}))
        payload["discrepancies"] = discrepancies
        return payload
    except Exception as e:
        logger.warning(f"Discrepancy detection failed (non-fatal): {e}", extra={"run_id": run_id})
        payload["discrepancies"] = []
        return payload


def _describe_validation_error(exc: ValidationError) -> str:
    """Convert a Pydantic ValidationError into a plain-English user message.

    Each missing/invalid field becomes one bullet. The message guides the
    user to enter the value manually in the wizard rather than showing a
    raw Pydantic traceback.
    """
    field_msgs: list[str] = []
    for error in exc.errors():
        loc = " → ".join(str(part) for part in error["loc"])
        pydantic_msg = error.get("msg", "invalid value")
        field_msgs.append(f"  • {loc}: {pydantic_msg}")

    fields_block = "\n".join(field_msgs)
    return (
        f"Could not run calculations — {len(field_msgs)} required field(s) are missing "
        f"or invalid:\n{fields_block}\n\n"
        "Please enter these values manually in the wizard and re-run the analysis."
    )


@shared_task(
    bind=True,
    soft_time_limit=settings.re_uw_task_soft_time_limit_seconds,
    acks_late=True,
    reject_on_worker_lost=True,
)
def re_calculate_underwriting_task(self, payload: dict) -> dict:
    """Run calculator, stress tests, rollover risk, verdict. Store result."""
    run_id = payload["run_id"]
    job_id = payload["job_id"]
    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)
    repo = UnderwritingRunRepository(db)

    try:
        tracker.update_progress(
            status="calculating", current_stage="calculation",
            progress_percent=80, message="Running calculations...",
        )
        inputs = SelfStorageInputs(**payload.get("merged_inputs", {}))
        doc_results = [ExtractedDocResult(**d) for d in payload.get("doc_results", [])]
        result = calculate(inputs)
        result.income_basis_months = inputs.operational.income_basis_months
        result.income_basis_note = inputs.operational.income_basis_note
        stress = run_stress_tests(inputs)
        result.stress_tests = stress
        result.unit_mix = _select_best_unit_mix(doc_results)
        if inputs.lease_records:
            result.rollover_risk = compute_rollover_risk(inputs.lease_records)
        verdict = evaluate(result, inputs.criteria, stress, _get_t12_period_months(doc_results), inputs=inputs)
        plausibility_warning = _build_plausibility_warning(payload.get("plausibility_flags", []))
        if plausibility_warning is not None:
            verdict.warnings.append(plausibility_warning)
            if verdict.status == "worth_pursuing":
                verdict.status = "needs_review"
            if plausibility_warning.message not in verdict.rationale:
                verdict.rationale = f"{verdict.rationale} Warning: {plausibility_warning.message}"

        discrepancy_warning = _build_discrepancy_warning(payload.get("discrepancies", []))
        if discrepancy_warning is not None:
            verdict.warnings.append(discrepancy_warning)
            if verdict.status == "worth_pursuing":
                verdict.status = "needs_review"
            if discrepancy_warning.message not in verdict.rationale:
                verdict.rationale = f"{verdict.rationale} Warning: {discrepancy_warning.message}"

        tracker.update_progress(
            status="completed", current_stage="storage",
            progress_percent=95, message="Storing results...",
        )
        typed_metrics = {
            "irr": result.irr,
            "cash_on_cash": result.cash_on_cash,
            "equity_multiple": result.equity_multiple,
            "dscr_year_one": result.dscr_year_one,
            "ltv": result.ltv,
            "cap_rate_year_one": result.cap_rate_year_one,
            "cap_rate_pro_forma": result.cap_rate_pro_forma,
            "noi_year_one": result.noi_year_one,
            "total_profit": result.total_profit,
            "monthly_cashflow": result.monthly_cashflow,
            "verdict_status": verdict.status,
            "verdict_failures": [f.model_dump() for f in verdict.failures],
        }
        result_payload = result.model_dump()
        result_payload["verdict"] = verdict.model_dump()
        if inputs.rent_comps:
            result_payload["rent_comps"] = [row.model_dump() for row in inputs.rent_comps]
        result_payload.update(_build_source_artifact_data(doc_results, payload.get("plausibility_flags", [])))
        om, t12 = _get_extracted_om_t12(doc_results)
        result_payload["noi_bridge"] = build_noi_bridge(inputs, om, t12, result)
        repo.update_result(run_id, result_payload, typed_metrics)
        repo.update_extraction(
            run_id,
            inputs=payload.get("merged_inputs", {}),
            field_citations=payload.get("field_citations", {}),
            discrepancies=payload.get("discrepancies", []),
            citation_context=payload.get("citation_context", {}),
        )
        tracker.mark_completed()

        # Log shadow credits for billing visibility
        try:
            run_obj = repo.get_by_id(run_id)
            if run_obj:
                from app.repositories.user_repository import UserRepository
                from app.services.beta_limits import log_shadow_credits
                user = UserRepository().get_user(run_obj.user_id)
                if user:
                    log_shadow_credits(
                        user=user,
                        operation_type="re_underwriting_run",
                        reference_id=run_id,
                        metadata={"asset_type": run_obj.asset_type},
                    )
        except Exception as e:
            logger.warning(f"Shadow credit logging failed for run {run_id}: {e}")

        return {"run_id": run_id, "status": "completed"}

    except SoftTimeLimitExceeded:
        tracker.mark_error(
            error_stage="calculation", error_message="Calculation timed out",
            internal_error="SoftTimeLimitExceeded", error_type="timeout", is_retryable=False,
        )
        repo.update_status(run_id, "failed", "Calculation timed out")
        raise
    except Exception as e:
        logger.error(f"Calculation failed: {e}", extra={"run_id": run_id})
        tracker.mark_error(
            error_stage="calculation", error_message="Calculation failed",
            internal_error=str(e)[:1000], error_type="calculation_error", is_retryable=False,
        )
        repo.update_status(run_id, "failed", str(e)[:500])
        raise


def start_re_underwriting_chain(
    run_id: str,
    doc_specs: list[dict],
    job_id: str,
) -> str:
    """Build and launch the underwriting chord.

    doc_specs: [{document_id: str, doc_type: "om"|"t12"|"rent_roll"}]
    Passes only IDs through Redis — tasks fetch their own chunks.
    """
    payloads = [
        {
            "run_id": run_id,
            "job_id": job_id,
            "doc_type": spec["doc_type"],
            "document_id": spec["document_id"],
            "source_index": i + 1,
        }
        for i, spec in enumerate(doc_specs)
    ]

    chord(
        group(re_extract_per_doc_task.s(p) for p in payloads),
        chain(
            re_merge_extractions_task.s(),
            re_detect_discrepancies_task.s(),
            re_calculate_underwriting_task.s(),
        ),
    ).apply_async(queue="critical")

    logger.info(f"RE underwriting chain started: {run_id}", extra={"doc_count": len(doc_specs)})
    return job_id
