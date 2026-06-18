"""Fixtures for underwriting API integration tests."""
import sys
import types
from uuid import uuid4
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.database import get_db
from app.repositories.re_underwriting_repo import UnderwritingRunRepository

try:
    import prometheus_client  # noqa: F401
except ModuleNotFoundError:
    # Local-test fallback: keep integration tests runnable without optional metrics deps.
    class _MetricStub:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            return None

        def observe(self, *args, **kwargs):
            return None

        def set(self, *args, **kwargs):
            return None

    prometheus_stub = types.ModuleType("prometheus_client")
    prometheus_stub.Counter = lambda *args, **kwargs: _MetricStub()
    prometheus_stub.Histogram = lambda *args, **kwargs: _MetricStub()
    sys.modules["prometheus_client"] = prometheus_stub

from app.verticals.real_estate.api.underwriting import router as underwriting_router


@pytest.fixture
def mock_user():
    """Minimal user with real_estate vertical access."""
    return SimpleNamespace(
        id=str(uuid4()),
        org_id=str(uuid4()),
        tier="pro",
        allowed_verticals=["real_estate"],
    )


@pytest.fixture
def api_client(db_session, mock_user):
    """TestClient with auth and DB overrides."""
    app = FastAPI()
    app.include_router(underwriting_router, prefix="/api/v1/re")

    app.dependency_overrides[get_current_user] = lambda: mock_user

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    client = TestClient(app)
    yield client

    # Cleanup
    app.dependency_overrides.clear()


@pytest.fixture
def completed_run(db_session):
    """A fully-completed UnderwritingRun with result_artifact — used by memo task tests."""
    from app.db_models_re import UnderwritingRun

    run = UnderwritingRun(
        id="test-run-memo",
        user_id="test-user-memo",
        name="Memo Test",
        asset_type="self_storage",
        address="123 Test Ave",
        document_ids=["doc-om-1"],
        inputs={
            "project": {
                "name": "Memo Test",
                "asset_type": "self_storage",
                "address": "123 Test Ave",
                "num_units": 400,
                "rentable_sqft": 50_000,
                "year_built": 2010,
                "population_3mi": 60_000,
                "avg_household_income_3mi": 75_000.0,
                "storage_sqft_per_capita_3mi": 7.5,
                "nearby_storage_count_1mi": 2,
                "nearby_storage_count_3mi": 6,
                "nearby_storage_count_5mi": 11,
            },
            "acquisition": {
                "purchase_price": 5_000_000.0,
                "closing_cost_pct": 0.02,
                "capex_reserve_per_unit": 100.0,
                "market_cap_rate_purchase": 0.07,
            },
            "operational": {
                "gross_potential_rent_annual": 800_000.0,
                "vacancy_credit_loss_pct": 0.10,
                "other_income_annual": 0.0,
                "mgmt_fee_pct": 0.06,
                "opex_growth_pct": 0.02,
                "rent_growth_pct": 0.03,
                "insurance_annual": 0.0,
                "noi_year_one_stated": 400_000.0,
            },
            "financing": {
                "ltv_pct": 0.65,
                "interest_rate_pct": 0.065,
                "amortization_years": 25,
                "loan_term_years": 10,
            },
            "exit": {
                "hold_period_years": 10,
                "exit_cap_rate": 0.065,
                "selling_cost_pct": 0.03,
            },
            "criteria": {
                "target_irr": 0.15,
                "target_cash_on_cash": 0.08,
                "max_ltv": 0.65,
                "dscr_year_one_floor": 1.25,
            },
            "unit_mix": [
                {"size": "10x10", "num_units": 100, "climate_type": "CC", "current_rent": 120.0},
                {"size": "10x10", "num_units": 300, "climate_type": "NC", "current_rent": 90.0},
            ],
            "rent_comps": [],
        },
        result_artifact={
            "noi_buildup": {
                "gpr": 800_000.0,
                "vacancy": 80_000.0,
                "egi": 720_000.0,
                "opex": 320_000.0,
                "noi": 400_000.0,
            },
            "return_metrics": {
                "irr": 0.18,
                "coc": 0.09,
                "em": 2.1,
                "dscr": 1.45,
                "dy": 0.092,
                "breakeven_occ": 0.78,
            },
            "noi_year_one": 400_000.0,
            "noi_bridge": {
                "om_stated": 410_000.0,
                "modeled": 400_000.0,
                "delta": -10_000.0,
            },
            "rent_position": {"cc_vs_market_pct": -0.02, "nc_vs_market_pct": 0.01},
            "sensitivity": {
                "matrix": [[400_000.0, 380_000.0], [420_000.0, 400_000.0]],
            },
            "stress_tests": {"dscr_year_3": 1.15},
            "rollover": {"max_window_pct": 0.18},
            "max_loan": {
                "max_loan": 3_250_000.0,
                "binding_constraint": "ltv",
                "delta_vs_current": 0.0,
                "current_loan": 3_250_000.0,
                "max_loan_by_dscr": 3_948_000.0,
                "max_loan_by_ltv": 3_250_000.0,
                "max_loan_by_debt_yield": 5_000_000.0,
            },
            "verdict": {
                "classification": "Pursue",
                "warnings": ["DSCR slack is thin in stress case"],
                "rationale": "All return metrics exceed criteria.",
            },
        },
        status="completed",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    yield run
    try:
        db_session.delete(run)
        db_session.commit()
    except Exception:
        db_session.rollback()


@pytest.fixture
def run_factory(db_session, mock_user):
    """Factory to create UnderwritingRun rows directly in DB."""

    def _create(**overrides):
        repo = UnderwritingRunRepository(db_session)

        run = repo.create(
            user_id=mock_user.id,
            name=overrides.get("name", "Test Storage"),
            asset_type=overrides.get("asset_type", "self_storage"),
            address=overrides.get("address", None),
            document_ids=overrides.get("document_ids", []),
        )

        if "status" in overrides:
            repo.update_status(run.id, overrides["status"])

        if "inputs" in overrides:
            repo.update_inputs(run.id, mock_user.id, overrides["inputs"])

        if "result_artifact" in overrides:
            repo.update_result(
                run.id,
                overrides["result_artifact"],
                overrides.get("typed_metrics", {}),
            )

        db_session.refresh(run)
        return run

    return _create
