"""Real Estate Underwriting API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Any, List, Optional
from pydantic import BaseModel, ValidationError
from app.database import get_db
from app.repositories.document_repository import DocumentRepository
from app.repositories.re_underwriting_repo import UnderwritingRunRepository
from app.repositories.job_repository import JobRepository
from app.auth import get_current_user
from app.db_models_users import User
from app.utils.logging import logger
from app.verticals.real_estate.underwriting.extraction.tasks.tasks import start_re_underwriting_chain
from app.verticals.real_estate.underwriting.schemas.self_storage import SelfStorageInputs, UnitMixRow
from app.verticals.real_estate.underwriting.calculator import calculate, calculate_sensitivity
from app.verticals.real_estate.underwriting.max_loan import compute_max_loan_for_run
from app.verticals.real_estate.underwriting.noi_bridge import build_noi_bridge
from app.verticals.real_estate.underwriting.stress_tests import run_stress_tests
from app.verticals.real_estate.underwriting.rollover import compute_rollover_risk
from app.repositories.user_repository import UserRepository
from app.schemas.user_thresholds import UserUnderwritingThresholds
from app.verticals.real_estate.underwriting.verdict import evaluate
from app.verticals.real_estate.underwriting.result_artifact import (
    get_preserved_unit_mix,
    merge_preserved_result_artifact,
)
from app.verticals.real_estate.underwriting.schemas.self_storage import (
    FormulaMetadata,
)

router = APIRouter(prefix="/underwriting", tags=["re_underwriting"])

class CreateUnderwritingRunRequest(BaseModel):
    name: str
    asset_type: str = "self_storage"
    address: Optional[str] = None
    documents: List[dict]

class UpdateInputsRequest(BaseModel):
    inputs: dict
    field_citations: Optional[dict] = None


class UpdateRunMetadataRequest(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None


class SensitivityRequest(BaseModel):
    purchase_prices: List[float]

class ScenarioOverrides(BaseModel):
    """Partial inputs for a what-if scenario recalculation. Only provided fields are overridden."""
    exit_cap_rate: Optional[float] = None
    vacancy_credit_loss_pct: Optional[float] = None
    rent_growth_pct: Optional[float] = None
    interest_rate_pct: Optional[float] = None
    purchase_price: Optional[float] = None


class MaxLoanRequest(BaseModel):
    """Optional overrides for max-loan sizing. Missing fields fall back to inputs.criteria, then to industry defaults."""
    dscr_floor: Optional[float] = None
    max_ltv: Optional[float] = None
    debt_yield_floor: Optional[float] = None


def _normalize_empty_strings(payload: Any) -> Any:
    """Convert blank form strings to None so optional numeric fields validate cleanly."""
    if isinstance(payload, dict):
        return {key: _normalize_empty_strings(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_normalize_empty_strings(item) for item in payload]
    if isinstance(payload, str) and payload.strip() == "":
        return None
    return payload


def _safe_validation_error_detail(exc: ValidationError) -> dict:
    """Return user-safe validation details without leaking backend internals."""
    invalid_fields: list[str] = []
    for item in exc.errors():
        loc = item.get("loc") or ()
        if isinstance(loc, tuple):
            field_path = ".".join(str(part) for part in loc if part != "inputs")
            if field_path:
                invalid_fields.append(field_path)

    deduped_fields = list(dict.fromkeys(invalid_fields))
    detail: dict[str, Any] = {
        "message": "Some underwriting inputs are invalid. Please review highlighted fields and try again.",
    }
    if deduped_fields:
        detail["fields"] = deduped_fields
    return detail


def _get_t12_period_months_from_artifact(existing_artifact: dict | None) -> int | None:
    if not existing_artifact:
        return None
    summary = (existing_artifact.get("t12_data") or {}).get("summary") or {}
    period_months = summary.get("period_months")
    return period_months if isinstance(period_months, int) and period_months > 0 else None


def _load_user_thresholds(user_id: str) -> UserUnderwritingThresholds | None:
    saved = UserRepository().get_underwriting_thresholds(user_id) or {}
    return UserUnderwritingThresholds(**saved) if saved else None


def _snapshot_thresholds_into_criteria(inputs_payload: dict, user_id: str) -> dict:
    """Fill any None verdict-gate fields in criteria from the user's current defaults.

    Called once at run creation / first save so the thresholds are frozen per-deal.
    Fields that are already set (non-None) are never overwritten.
    """
    thresholds = _load_user_thresholds(user_id)
    if not thresholds:
        return inputs_payload
    criteria = inputs_payload.get("criteria", {})
    for key in ("dscr_year_one_floor", "stress_dscr_floor", "rollover_risk_pct"):
        if criteria.get(key) is None:
            val = getattr(thresholds, key, None)
            if val is not None:
                criteria[key] = val
    return {**inputs_payload, "criteria": criteria}


def _source_documents_for_run(document_ids: list[dict] | None, org_id: str | None) -> list[dict]:
    """Attach display metadata to saved underwriting source document specs."""
    source_specs = [
        doc for doc in (document_ids or [])
        if isinstance(doc, dict) and doc.get("document_id") and doc.get("doc_type")
    ]
    if not source_specs:
        return []

    metadata = DocumentRepository().get_doc_metadata_by_ids(
        [doc["document_id"] for doc in source_specs],
        org_id,
    )
    metadata_by_id = {doc["id"]: doc for doc in metadata}

    return [
        {
            **doc,
            "name": metadata_by_id.get(doc["document_id"], {}).get("filename"),
            "filename": metadata_by_id.get(doc["document_id"], {}).get("filename"),
            "page_count": metadata_by_id.get(doc["document_id"], {}).get("page_count"),
            "file_size_bytes": metadata_by_id.get(doc["document_id"], {}).get("file_size_bytes"),
        }
        for doc in source_specs
    ]


def _calculate_and_store_result(
    repo: UnderwritingRunRepository,
    run_id: str,
    inputs_payload: dict,
) -> None:
    """Recalculate underwriting outputs from saved inputs and persist the result artifact."""
    existing_run = repo.get_by_id(run_id)
    existing_artifact = existing_run.result_artifact if existing_run else None

    inputs = SelfStorageInputs(**inputs_payload)
    result = calculate(inputs)
    result.income_basis_months = inputs.operational.income_basis_months
    result.income_basis_note = inputs.operational.income_basis_note

    # Add current_expense_ratio metadata (not produced by the calculator)
    result.formula_metadata["current_expense_ratio"] = FormulaMetadata(
        description="Total operating expenses ÷ effective gross income from the trailing 12-month income statement.",
    )

    stress_tests = run_stress_tests(inputs)
    result.stress_tests = stress_tests
    effective_unit_mix = inputs.unit_mix or [
        UnitMixRow.model_validate(row)
        for row in get_preserved_unit_mix(existing_artifact)
    ]
    result.unit_mix = effective_unit_mix
    if inputs.lease_records:
        result.rollover_risk = compute_rollover_risk(inputs.lease_records)

    verdict = evaluate(
        result,
        inputs.criteria,
        stress_tests,
        _get_t12_period_months_from_artifact(existing_artifact),
        inputs=inputs,
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
        "verdict_failures": [failure.model_dump() for failure in verdict.failures],
    }
    result_payload = result.model_dump()
    result_payload["verdict"] = verdict.model_dump()
    if inputs.rent_comps:
        result_payload["rent_comps"] = [row.model_dump() for row in inputs.rent_comps]
    result_payload["noi_bridge"] = build_noi_bridge(
        inputs,
        om=None,
        t12=None,
        result=result,
        source_artifact=existing_artifact,
    )
    result_payload = merge_preserved_result_artifact(existing_artifact, result_payload)
    repo.update_result(run_id, result_payload, typed_metrics)

@router.post("/runs", response_model=dict)
def create_underwriting_run(payload: CreateUnderwritingRunRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = UnderwritingRunRepository(db)
    job_repo = JobRepository()
    try:
        run = repo.create(user_id=user.id, name=payload.name, asset_type=payload.asset_type, address=payload.address, document_ids=payload.documents)
        if not payload.documents:
            repo.update_status(run.id, "needs_review")
            logger.info(f"Created manual underwriting run: {run.id}", extra={"user_id": user.id})
            return {"run_id": run.id, "extraction_job_id": None, "status": "needs_review"}

        om_docs = [d for d in payload.documents if d.get("doc_type") == "om"]
        if not om_docs:
            raise ValueError("At least one document with doc_type 'om' is required to run extraction")

        job_state = job_repo.create_job(entity_type="underwriting_run", entity_id=run.id, status="extracting", current_stage="initialization", progress_percent=5, job_id=run.id)
        if not job_state:
            raise ValueError("Failed to create job state")
        doc_specs = [{"document_id": d["document_id"], "doc_type": d["doc_type"]} for d in payload.documents]
        start_re_underwriting_chain(run.id, doc_specs, run.id)
        logger.info(f"Created underwriting run: {run.id}", extra={"user_id": user.id})
        return {"run_id": run.id, "extraction_job_id": run.id, "status": "extracting"}
    except Exception as e:
        logger.error(f"Failed to create underwriting run: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/runs", response_model=dict)
def list_underwriting_runs(user: User = Depends(get_current_user), db: Session = Depends(get_db), limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    repo = UnderwritingRunRepository(db)
    runs = repo.list(user.id, limit=limit, offset=offset)
    return {"runs": [{"id": r.id, "name": r.name, "asset_type": r.asset_type, "address": r.address, "status": r.status, "irr": r.irr, "cash_on_cash": r.cash_on_cash, "equity_multiple": r.equity_multiple, "monthly_cashflow": r.monthly_cashflow, "verdict_status": r.verdict_status, "result_artifact": r.result_artifact, "created_at": r.created_at, "updated_at": r.updated_at} for r in runs]}

@router.get("/runs/{run_id}", response_model=dict)
def get_underwriting_run(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = UnderwritingRunRepository(db)
    run = repo.get(run_id, user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    source_documents = _source_documents_for_run(run.document_ids, user.org_id)
    return {"id": run.id, "name": run.name, "asset_type": run.asset_type, "address": run.address, "status": run.status, "document_ids": run.document_ids or [], "source_documents": source_documents, "inputs": run.inputs, "field_citations": run.field_citations, "citation_context": run.citation_context, "discrepancies": run.discrepancies, "result_artifact": run.result_artifact, "verdict_status": run.verdict_status, "verdict_failures": run.verdict_failures, "irr": run.irr, "cash_on_cash": run.cash_on_cash, "equity_multiple": run.equity_multiple, "dscr_year_one": run.dscr_year_one, "ltv": run.ltv, "cap_rate_year_one": run.cap_rate_year_one, "cap_rate_pro_forma": run.cap_rate_pro_forma, "noi_year_one": run.noi_year_one, "total_profit": run.total_profit, "monthly_cashflow": run.monthly_cashflow, "created_at": run.created_at, "updated_at": run.updated_at, "completed_at": run.completed_at}


@router.patch("/runs/{run_id}", response_model=dict)
def update_underwriting_run_metadata(run_id: str, payload: UpdateRunMetadataRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = UnderwritingRunRepository(db)
    updates: dict[str, str | None] = {}

    if "name" in payload.model_fields_set:
        name = (payload.name or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="Deal name is required")
        updates["name"] = name
    if "address" in payload.model_fields_set:
        address = (payload.address or "").strip()
        updates["address"] = address or None

    if updates:
        success = repo.update_metadata(run_id, user.id, updates)
        if not success:
            raise HTTPException(status_code=404, detail="Run not found")

    run = repo.get(run_id, user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"status": "updated", "run_id": run.id, "name": run.name, "address": run.address, "inputs": run.inputs}


@router.patch("/runs/{run_id}/inputs", response_model=dict)
def update_underwriting_inputs(run_id: str, payload: UpdateInputsRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = UnderwritingRunRepository(db)
    run = repo.get(run_id, user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    normalized_inputs = _normalize_empty_strings(payload.inputs)

    try:
        validated_inputs = SelfStorageInputs(**normalized_inputs)
    except ValidationError as exc:
        logger.warning(
            "Underwriting input validation failed",
            extra={"run_id": run_id, "user_id": user.id, "errors": exc.errors()},
        )
        raise HTTPException(status_code=422, detail=_safe_validation_error_detail(exc))

    # Snapshot user's current verdict-gate thresholds into criteria for any fields not explicitly set.
    # This freezes dscr_year_one_floor / stress_dscr_floor / rollover_risk_pct per-deal at first save.
    snapshotted = _snapshot_thresholds_into_criteria(validated_inputs.model_dump(), user.id)
    validated_inputs = SelfStorageInputs(**snapshotted)
    inputs_to_save = validated_inputs.model_dump()
    field_citations = payload.field_citations if payload.field_citations is not None else run.field_citations

    success = repo.update_inputs(run_id, user.id, inputs_to_save, field_citations=field_citations)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update inputs")

    try:
        _calculate_and_store_result(repo, run_id, inputs_to_save)
    except ValueError as e:
        logger.warning(f"Underwriting calculation validation failed for run {run_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to recalculate underwriting run {run_id}: {e}")
        raise HTTPException(status_code=400, detail="Failed to calculate underwriting result")

    logger.info(f"Updated and recalculated inputs for run: {run_id}", extra={"user_id": user.id})
    return {"status": "completed", "run_id": run_id, "inputs": inputs_to_save, "field_citations": field_citations}

@router.post("/runs/{run_id}/sensitivity", response_model=dict)
def sensitivity_analysis(run_id: str, payload: SensitivityRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = UnderwritingRunRepository(db)
    run = repo.get(run_id, user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if not run.inputs or not run.result_artifact:
        raise HTTPException(status_code=400, detail="Run not ready for sensitivity")
    try:
        inputs = SelfStorageInputs(**run.inputs)
        sensitivity_points = calculate_sensitivity(inputs, payload.purchase_prices)
        return {"sensitivity_points": [sp.model_dump() for sp in sensitivity_points]}
    except Exception as e:
        logger.error(f"Sensitivity analysis failed: {e}")
        raise HTTPException(status_code=400, detail="Sensitivity analysis failed")

@router.post("/runs/{run_id}/recalculate", response_model=dict)
def scenario_recalculate(run_id: str, payload: ScenarioOverrides, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Stateless what-if recalculation. Merges overrides into saved inputs, runs the calculator,
    and returns the result without writing to the database."""
    repo = UnderwritingRunRepository(db)
    run = repo.get(run_id, user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if not run.inputs:
        raise HTTPException(status_code=400, detail="Run has no saved inputs to recalculate from")
    try:
        inputs = SelfStorageInputs(**run.inputs)
        overrides = payload.model_dump(exclude_none=True)

        if "exit_cap_rate" in overrides:
            inputs = inputs.model_copy(update={"exit": inputs.exit.model_copy(update={"exit_cap_rate": overrides["exit_cap_rate"]})})
        if "vacancy_credit_loss_pct" in overrides:
            inputs = inputs.model_copy(update={"operational": inputs.operational.model_copy(update={"vacancy_credit_loss_pct": overrides["vacancy_credit_loss_pct"]})})
        if "rent_growth_pct" in overrides:
            inputs = inputs.model_copy(update={"operational": inputs.operational.model_copy(update={"rent_growth_pct": overrides["rent_growth_pct"]})})
        if "interest_rate_pct" in overrides:
            inputs = inputs.model_copy(update={"financing": inputs.financing.model_copy(update={"interest_rate_pct": overrides["interest_rate_pct"]})})
        if "purchase_price" in overrides:
            inputs = inputs.model_copy(update={"acquisition": inputs.acquisition.model_copy(update={"purchase_price": overrides["purchase_price"]})})

        result = calculate(inputs)
        stress = run_stress_tests(inputs)
        result.stress_tests = stress
        verdict = evaluate(result, inputs.criteria, stress, _get_t12_period_months_from_artifact(run.result_artifact), inputs=inputs)

        # Keep this stateless what-if response lean: the UI only needs scenario
        # metrics here. Persisted calculation paths build result_artifact.noi_bridge.
        return {
            "irr": result.irr,
            "cash_on_cash": result.cash_on_cash,
            "equity_multiple": result.equity_multiple,
            "dscr_year_one": result.dscr_year_one,
            "cap_rate_year_one": result.cap_rate_year_one,
            "noi_year_one": result.noi_year_one,
            "monthly_cashflow": result.monthly_cashflow,
            "break_even_occupancy_pct": result.break_even_occupancy_pct,
            "verdict_status": verdict.status,
            "verdict_failures": [f.model_dump() for f in verdict.failures],
            "projections": [p.model_dump() for p in result.projections],
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Scenario recalculate failed for run {run_id}: {e}")
        raise HTTPException(status_code=400, detail="Scenario calculation failed")


@router.post("/runs/{run_id}/max-loan", response_model=dict)
def max_loan_sizing(
    run_id: str,
    payload: MaxLoanRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stateless max-loan sizing. Pulls run state, applies optional constraint overrides,
    runs the max-loan calculator, and returns the result. No DB writes."""
    repo = UnderwritingRunRepository(db)
    run = repo.get(run_id, user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if not run.inputs:
        raise HTTPException(status_code=400, detail="Run has no saved inputs")

    # Validate inputs early so a malformed run returns a 400 instead of a 500.
    try:
        SelfStorageInputs(**run.inputs)
    except ValidationError as exc:
        logger.warning(f"Max-loan: run {run_id} inputs failed validation: {exc}")
        raise HTTPException(status_code=400, detail="Run inputs are not valid")

    try:
        result = compute_max_loan_for_run(
            run,
            dscr_floor=payload.dscr_floor,
            max_ltv=payload.max_ltv,
            debt_yield_floor=payload.debt_yield_floor,
        )
    except Exception as e:
        logger.error(f"Max-loan sizing failed for run {run_id}: {e}")
        raise HTTPException(status_code=400, detail="Max-loan calculation failed")

    if result is None:
        raise HTTPException(status_code=400, detail="Run has no saved inputs")

    return result.model_dump()


@router.delete("/runs/{run_id}", response_model=dict)
def delete_underwriting_run(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = UnderwritingRunRepository(db)
    success = repo.delete(run_id, user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Run not found")
    logger.info(f"Deleted underwriting run: {run_id}", extra={"user_id": user.id})
    return {"status": "deleted", "run_id": run_id}
