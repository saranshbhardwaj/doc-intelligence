"""Real Estate Underwriting API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from app.database import get_db
from app.repositories.re_underwriting_repo import UnderwritingRunRepository
from app.repositories.job_repository import JobRepository
from app.auth import get_current_user
from app.db_models_users import User
from app.utils.logging import logger
from app.verticals.real_estate.underwriting.extraction.tasks.tasks import start_re_underwriting_chain
from app.verticals.real_estate.underwriting.schemas.self_storage import SelfStorageInputs, UnitMixRow
from app.verticals.real_estate.underwriting.calculator import calculate, calculate_sensitivity
from app.verticals.real_estate.underwriting.stress_tests import run_stress_tests
from app.verticals.real_estate.underwriting.rollover import compute_rollover_risk
from app.verticals.real_estate.underwriting.verdict import evaluate
from app.verticals.real_estate.underwriting.result_artifact import (
    get_preserved_unit_mix,
    merge_preserved_result_artifact,
)

router = APIRouter(prefix="/underwriting", tags=["re_underwriting"])

class CreateUnderwritingRunRequest(BaseModel):
    name: str
    asset_type: str = "self_storage"
    address: Optional[str] = None
    documents: List[dict]

class UpdateInputsRequest(BaseModel):
    inputs: dict

class SensitivityRequest(BaseModel):
    purchase_prices: List[float]

class ScenarioOverrides(BaseModel):
    """Partial inputs for a what-if scenario recalculation. Only provided fields are overridden."""
    exit_cap_rate: Optional[float] = None
    vacancy_credit_loss_pct: Optional[float] = None
    rent_growth_pct: Optional[float] = None
    interest_rate_pct: Optional[float] = None
    purchase_price: Optional[float] = None


def _get_t12_period_months_from_artifact(existing_artifact: dict | None) -> int | None:
    if not existing_artifact:
        return None
    summary = (existing_artifact.get("t12_data") or {}).get("summary") or {}
    period_months = summary.get("period_months")
    return period_months if isinstance(period_months, int) and period_months > 0 else None


def _calculate_and_store_result(repo: UnderwritingRunRepository, run_id: str, inputs_payload: dict) -> None:
    """Recalculate underwriting outputs from saved inputs and persist the result artifact."""
    existing_run = repo.get_by_id(run_id)
    existing_artifact = existing_run.result_artifact if existing_run else None

    inputs = SelfStorageInputs(**inputs_payload)
    result = calculate(inputs)
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
    return {"id": run.id, "name": run.name, "asset_type": run.asset_type, "address": run.address, "status": run.status, "document_ids": run.document_ids or [], "inputs": run.inputs, "field_citations": run.field_citations, "citation_context": run.citation_context, "discrepancies": run.discrepancies, "result_artifact": run.result_artifact, "verdict_status": run.verdict_status, "verdict_failures": run.verdict_failures, "irr": run.irr, "cash_on_cash": run.cash_on_cash, "equity_multiple": run.equity_multiple, "dscr_year_one": run.dscr_year_one, "ltv": run.ltv, "cap_rate_year_one": run.cap_rate_year_one, "cap_rate_pro_forma": run.cap_rate_pro_forma, "noi_year_one": run.noi_year_one, "total_profit": run.total_profit, "monthly_cashflow": run.monthly_cashflow, "created_at": run.created_at, "updated_at": run.updated_at, "completed_at": run.completed_at}

@router.patch("/runs/{run_id}/inputs", response_model=dict)
def update_underwriting_inputs(run_id: str, payload: UpdateInputsRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = UnderwritingRunRepository(db)
    run = repo.get(run_id, user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        validated_inputs = SelfStorageInputs(**payload.inputs)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid underwriting inputs: {e}")

    success = repo.update_inputs(run_id, user.id, validated_inputs.model_dump())
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update inputs")

    try:
        _calculate_and_store_result(repo, run_id, validated_inputs.model_dump())
    except Exception as e:
        logger.error(f"Failed to recalculate underwriting run {run_id}: {e}")
        raise HTTPException(status_code=400, detail="Failed to calculate underwriting result")

    logger.info(f"Updated and recalculated inputs for run: {run_id}", extra={"user_id": user.id})
    return {"status": "completed", "run_id": run_id}

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


@router.delete("/runs/{run_id}", response_model=dict)
def delete_underwriting_run(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = UnderwritingRunRepository(db)
    success = repo.delete(run_id, user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Run not found")
    logger.info(f"Deleted underwriting run: {run_id}", extra={"user_id": user.id})
    return {"status": "deleted", "run_id": run_id}
