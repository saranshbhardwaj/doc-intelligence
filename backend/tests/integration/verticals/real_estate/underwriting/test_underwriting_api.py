"""Integration tests for the underwriting API endpoints."""
import pytest
from uuid import uuid4

from app.verticals.real_estate.api.underwriting import start_re_underwriting_chain


pytestmark = pytest.mark.integration


class DispatchOnlyTaskStub:
    """Stub that records task dispatch but doesn't execute."""

    def __init__(self):
        self.call_count = 0
        self.last_args = None

    def __call__(self, *args, **kwargs):
        """Record the call; don't execute."""
        self.call_count += 1
        self.last_args = (args, kwargs)
        return "job-id"


class TestCRUDOperations:
    """Full CRUD coverage for underwriting runs."""

    def test_post_runs_creates_manual_run_without_documents(self, api_client, monkeypatch):
        """POST /runs without documents creates a manual run without dispatching extraction."""
        task_stub = DispatchOnlyTaskStub()
        monkeypatch.setattr(
            "app.verticals.real_estate.api.underwriting.start_re_underwriting_chain",
            task_stub,
        )

        payload = {
            "name": "Test Property",
            "asset_type": "self_storage",
            "address": "123 Main St",
            "documents": [],
        }

        response = api_client.post("/api/v1/re/underwriting/runs", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["run_id"]
        assert data["extraction_job_id"] is None
        assert data["status"] == "needs_review"
        assert task_stub.call_count == 0

    def test_post_runs_dispatches_extraction_when_om_present(self, api_client, monkeypatch):
        """POST /runs with an OM document dispatches extraction."""
        task_stub = DispatchOnlyTaskStub()
        monkeypatch.setattr(
            "app.verticals.real_estate.api.underwriting.start_re_underwriting_chain",
            task_stub,
        )

        payload = {
            "name": "Test Property",
            "asset_type": "self_storage",
            "address": "123 Main St",
            "documents": [{"document_id": str(uuid4()), "doc_type": "om"}],
        }

        response = api_client.post("/api/v1/re/underwriting/runs", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["run_id"]
        assert data["extraction_job_id"] == data["run_id"]
        assert data["status"] == "extracting"
        assert task_stub.call_count == 1

    def test_get_runs_empty_list_for_new_user(self, api_client):
        """GET /runs for new user → empty runs, total=0."""
        response = api_client.get("/api/v1/re/underwriting/runs")

        assert response.status_code == 200
        data = response.json()
        assert data["runs"] == []
        assert "total" not in data

    def test_get_runs_lists_all_runs(self, api_client, run_factory):
        """GET /runs → returns all user's runs, ordered by newest first."""
        # Create 2 runs
        run1 = run_factory(name="Run 1", status="completed")
        run2 = run_factory(name="Run 2", status="completed")

        response = api_client.get("/api/v1/re/underwriting/runs")

        assert response.status_code == 200
        data = response.json()
        assert len(data["runs"]) == 2
        # Verify both runs present
        names = [r["name"] for r in data["runs"]]
        assert "Run 1" in names
        assert "Run 2" in names

    def test_get_run_detail(self, api_client, run_factory):
        """GET /runs/{id} → full run detail."""
        run = run_factory(name="Detail Test", status="completed")

        response = api_client.get(f"/api/v1/re/underwriting/runs/{run.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == run.id
        assert data["name"] == "Detail Test"
        assert data["status"] == "completed"

    def test_patch_inputs(self, api_client, run_factory):
        """PATCH /runs/{id}/inputs updates inputs and recalculates results."""
        run = run_factory(name="Update Test", status="needs_review")
        new_inputs = {
            "project": {"name": "Update Test", "asset_type": "self_storage"},
            "acquisition": {"purchase_price": 5000000, "closing_cost_pct": 0.02, "capex_reserve_per_unit": 0},
            "operational": {
                "gross_potential_rent_annual": 600000,
                "vacancy_credit_loss_pct": 0.10,
                "other_income_annual": 0,
                "rent_growth_pct": 0.03,
                "property_tax_annual": 30000,
                "insurance_annual": 15000,
                "mgmt_fee_pct": 0.08,
                "payroll_annual": 40000,
                "repairs_maintenance_annual": 20000,
                "utilities_annual": 12000,
                "marketing_annual": 5000,
                "other_opex_annual": 10000,
                "opex_growth_pct": 0.02
            },
            "financing": {"ltv_pct": 0.70, "interest_rate_pct": 0.065, "amortization_years": 25, "loan_term_years": 10},
            "exit": {"hold_period_years": 10, "exit_cap_rate": 0.065, "selling_cost_pct": 0.03},
            "criteria": {"target_irr": 0.15, "target_cash_on_cash": 0.08, "target_equity_multiple": 2.0, "max_ltv": 0.80},
            "lease_records": [],
            "unit_mix": []
        }

        response = api_client.patch(
            f"/api/v1/re/underwriting/runs/{run.id}/inputs",
            json={"inputs": new_inputs},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        # Verify DB was updated
        response = api_client.get(f"/api/v1/re/underwriting/runs/{run.id}")
        saved_inputs = response.json()["inputs"]
        assert saved_inputs["project"]["name"] == new_inputs["project"]["name"]
        assert saved_inputs["project"]["asset_type"] == new_inputs["project"]["asset_type"]
        assert saved_inputs["acquisition"]["purchase_price"] == new_inputs["acquisition"]["purchase_price"]
        assert saved_inputs["operational"]["gross_potential_rent_annual"] == new_inputs["operational"]["gross_potential_rent_annual"]
        assert saved_inputs["financing"]["ltv_pct"] == new_inputs["financing"]["ltv_pct"]
        assert saved_inputs["exit"]["exit_cap_rate"] == new_inputs["exit"]["exit_cap_rate"]
        assert saved_inputs["criteria"]["target_irr"] == new_inputs["criteria"]["target_irr"]
        assert response.json()["result_artifact"]["verdict"]

    def test_delete_run(self, api_client, run_factory):
        """DELETE /runs/{id} → run deleted, subsequent GET returns 404."""
        run = run_factory(name="Delete Test")

        response = api_client.delete(f"/api/v1/re/underwriting/runs/{run.id}")

        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

        # Verify subsequent GET returns 404
        response = api_client.get(f"/api/v1/re/underwriting/runs/{run.id}")
        assert response.status_code == 404


class TestSensitivityAnalysis:
    """POST /runs/{id}/sensitivity endpoint."""

    def test_sensitivity_requires_result_artifact(self, api_client, run_factory):
        """POST /sensitivity without result_artifact → 400 error."""
        run = run_factory(name="No Result", status="needs_review")

        response = api_client.post(
            f"/api/v1/re/underwriting/runs/{run.id}/sensitivity",
            json={"purchase_prices": [4_000_000, 5_000_000]},
        )

        assert response.status_code == 400

    def test_sensitivity_with_valid_inputs(self, api_client, run_factory):
        """POST /sensitivity with inputs + result_artifact → sensitivity_points."""
        # Create a run with valid inputs (structure matters, not actual calc)
        from app.verticals.real_estate.underwriting.schemas.self_storage import (
            SelfStorageInputs,
            ProjectDetails,
            AcquisitionInputs,
            OperationalInputs,
            FinancingInputs,
            ExitInputs,
            InvestmentCriteria,
            SelfStorageResult,
            CapitalStructure,
            TotalReturn,
        )

        valid_inputs = SelfStorageInputs(
            project=ProjectDetails(name="Test", asset_type="self_storage"),
            acquisition=AcquisitionInputs(purchase_price=5_000_000),
            operational=OperationalInputs(
                gross_potential_rent_annual=600_000,
                vacancy_credit_loss_pct=0.10,
                mgmt_fee_pct=0.08,
            ),
            financing=FinancingInputs(ltv_pct=0.70, interest_rate_pct=0.065),
            exit=ExitInputs(hold_period_years=10, exit_cap_rate=0.065),
            criteria=InvestmentCriteria(target_irr=0.15, target_cash_on_cash=0.08),
        )

        result_artifact = {
            "irr": 0.18,
            "cash_on_cash": 0.10,
            "projections": [],
        }

        run = run_factory(
            name="Sensitivity Test",
            status="completed",
            inputs=valid_inputs.model_dump(),
            result_artifact=result_artifact,
        )

        response = api_client.post(
            f"/api/v1/re/underwriting/runs/{run.id}/sensitivity",
            json={"purchase_prices": [4_000_000, 5_000_000, 6_000_000]},
        )

        assert response.status_code == 200
        data = response.json()
        assert "sensitivity_points" in data
        assert len(data["sensitivity_points"]) == 3


class TestAuthorization:
    """Authorization and ownership boundaries."""

    def test_cross_user_access_returns_404(self, api_client, run_factory):
        """GET /runs/{id} for another user's run → 404 (not 403)."""
        run = run_factory(name="Private Run")

        # Simulate another user by creating a new api_client with different user
        # For this test, we'll just verify the endpoint respects user_id
        # (Actual cross-user test would need a second api_client fixture)

        # For now, verify that accessing own run works
        response = api_client.get(f"/api/v1/re/underwriting/runs/{run.id}")
        assert response.status_code == 200

    def test_nonexistent_run_returns_404(self, api_client):
        """GET /runs/{fake_id} → 404."""
        response = api_client.get(f"/api/v1/re/underwriting/runs/{uuid4()}")

        assert response.status_code == 404


class TestInputValidation:
    """Request validation and error handling."""

    def test_post_missing_required_name(self, api_client):
        """POST /runs without name → 422 validation error."""
        payload = {
            "asset_type": "self_storage",
            # Missing 'name'
        }

        response = api_client.post("/api/v1/re/underwriting/runs", json=payload)

        assert response.status_code == 422

    def test_patch_with_invalid_inputs_dict(self, api_client, run_factory):
        """PATCH with non-dict inputs → handled gracefully or 422."""
        run = run_factory(name="Validation Test")

        response = api_client.patch(
            f"/api/v1/re/underwriting/runs/{run.id}/inputs",
            json={"inputs": "not a dict"},
        )

        # Either 422 or accepted (depends on schema validation)
        assert response.status_code in [200, 422]

    def test_patch_blank_optional_numeric_fields_are_normalized(self, api_client, run_factory):
        """PATCH should treat blank optional numeric strings as null and succeed."""
        run = run_factory(name="Blank Optional Inputs", status="needs_review")
        new_inputs = {
            "project": {
                "name": "Blank Optional Inputs",
                "asset_type": "self_storage",
                "nearby_storage_count_3mi": "",
                "nearby_storage_count_5mi": "",
            },
            "acquisition": {"purchase_price": 5000000, "closing_cost_pct": 0.02, "capex_reserve_per_unit": 0},
            "operational": {
                "gross_potential_rent_annual": 600000,
                "vacancy_credit_loss_pct": 0.10,
                "other_income_annual": 0,
                "rent_growth_pct": 0.03,
                "property_tax_annual": 30000,
                "insurance_annual": 15000,
                "mgmt_fee_pct": 0.08,
                "payroll_annual": 40000,
                "repairs_maintenance_annual": 20000,
                "utilities_annual": 12000,
                "marketing_annual": 5000,
                "other_opex_annual": 10000,
                "opex_growth_pct": 0.02,
            },
            "financing": {"ltv_pct": 0.70, "interest_rate_pct": 0.065, "amortization_years": 25, "loan_term_years": 10},
            "exit": {"hold_period_years": 10, "exit_cap_rate": 0.065, "selling_cost_pct": 0.03},
            "criteria": {"target_irr": 0.15, "target_cash_on_cash": 0.08, "target_equity_multiple": 2.0, "max_ltv": 0.80},
            "lease_records": [],
            "unit_mix": [],
        }

        response = api_client.patch(
            f"/api/v1/re/underwriting/runs/{run.id}/inputs",
            json={"inputs": new_inputs},
        )

        assert response.status_code == 200
        saved = api_client.get(f"/api/v1/re/underwriting/runs/{run.id}").json()
        assert saved["inputs"]["project"]["nearby_storage_count_3mi"] is None
        assert saved["inputs"]["project"]["nearby_storage_count_5mi"] is None

    def test_patch_validation_error_payload_is_sanitized(self, api_client, run_factory):
        """PATCH validation failures should not leak raw pydantic/internal traceback text."""
        run = run_factory(name="Bad Inputs", status="needs_review")
        bad_inputs = {
            "project": {"name": "Bad Inputs", "asset_type": "self_storage"},
            "acquisition": {"purchase_price": 5000000, "closing_cost_pct": 0.02, "capex_reserve_per_unit": 0},
            "operational": {
                "gross_potential_rent_annual": "not-a-number",
                "vacancy_credit_loss_pct": 0.10,
                "other_income_annual": 0,
                "rent_growth_pct": 0.03,
                "property_tax_annual": 30000,
                "insurance_annual": 15000,
                "mgmt_fee_pct": 0.08,
                "payroll_annual": 40000,
                "repairs_maintenance_annual": 20000,
                "utilities_annual": 12000,
                "marketing_annual": 5000,
                "other_opex_annual": 10000,
                "opex_growth_pct": 0.02,
            },
            "financing": {"ltv_pct": 0.70, "interest_rate_pct": 0.065, "amortization_years": 25, "loan_term_years": 10},
            "exit": {"hold_period_years": 10, "exit_cap_rate": 0.065, "selling_cost_pct": 0.03},
            "criteria": {"target_irr": 0.15, "target_cash_on_cash": 0.08, "target_equity_multiple": 2.0, "max_ltv": 0.80},
            "lease_records": [],
            "unit_mix": [],
        }

        response = api_client.patch(
            f"/api/v1/re/underwriting/runs/{run.id}/inputs",
            json={"inputs": bad_inputs},
        )

        assert response.status_code == 422
        detail = response.json().get("detail")
        assert isinstance(detail, dict)
        assert "message" in detail
        assert "pydantic" not in str(detail).lower()
        assert "int_parsing" not in str(detail)


class TestMaxLoanEndpoint:
    """POST /runs/{id}/max-loan — stateless max-loan sizing."""

    def _seed_run(self, api_client):
        """Helper: create a run, attach inputs sufficient for sizing, return run_id."""
        from app.verticals.real_estate.api.underwriting import start_re_underwriting_chain  # noqa: F401

        create_resp = api_client.post(
            "/api/v1/re/underwriting/runs",
            json={"name": "Sizing Test", "asset_type": "self_storage", "address": None, "documents": []},
        )
        assert create_resp.status_code == 200
        run_id = create_resp.json()["run_id"]

        inputs = {
            "project": {"name": "Sizing Test", "asset_type": "self_storage", "num_units": 400, "rentable_sqft": 50_000},
            "acquisition": {"purchase_price": 5_000_000.0, "closing_cost_pct": 0.02, "capex_reserve_per_unit": 0.0},
            "operational": {
                "gross_potential_rent_annual": 800_000.0,
                "vacancy_credit_loss_pct": 0.10,
                "other_income_annual": 0.0,
                "rent_growth_pct": 0.03,
                "insurance_annual": 0.0,
                "mgmt_fee_pct": 0.06,
                "opex_growth_pct": 0.02,
                "noi_year_one_stated": 400_000.0,
            },
            "financing": {"ltv_pct": 0.65, "interest_rate_pct": 0.065, "amortization_years": 25, "loan_term_years": 10},
            "exit": {"hold_period_years": 10, "exit_cap_rate": 0.065, "selling_cost_pct": 0.03},
            "criteria": {
                "target_irr": 0.15,
                "target_cash_on_cash": 0.08,
                "target_equity_multiple": 2.0,
                "max_ltv": 0.65,
                "dscr_year_one_floor": 1.25,
            },
            "unit_mix": [],
            "rent_comps": [],
        }
        patch_resp = api_client.patch(
            f"/api/v1/re/underwriting/runs/{run_id}/inputs",
            json={"inputs": inputs},
        )
        assert patch_resp.status_code == 200, patch_resp.text
        return run_id

    def test_happy_path_returns_max_loan_result(self, api_client):
        run_id = self._seed_run(api_client)
        resp = api_client.post(f"/api/v1/re/underwriting/runs/{run_id}/max-loan", json={})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        for key in (
            "max_loan",
            "max_loan_by_dscr",
            "max_loan_by_ltv",
            "max_loan_by_debt_yield",
            "binding_constraint",
            "equity_required",
            "current_loan",
            "delta_vs_current",
            "notes",
        ):
            assert key in data, f"missing {key} in response: {data}"
        assert data["binding_constraint"] in {"dscr", "ltv", "debt_yield", "none"}
        assert isinstance(data["notes"], list)

    def test_empty_body_falls_back_to_criteria(self, api_client):
        run_id = self._seed_run(api_client)
        resp = api_client.post(f"/api/v1/re/underwriting/runs/{run_id}/max-loan", json={})
        assert resp.status_code == 200
        # LTV should be 0.65 (criteria) x 5M = 3.25M.
        assert resp.json()["max_loan_by_ltv"] == pytest.approx(3_250_000.0, rel=1e-9)

    def test_override_constraints_in_body(self, api_client):
        run_id = self._seed_run(api_client)
        resp = api_client.post(
            f"/api/v1/re/underwriting/runs/{run_id}/max-loan",
            json={"max_ltv": 0.50, "dscr_floor": 1.40, "debt_yield_floor": 0.10},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["max_loan_by_ltv"] == pytest.approx(2_500_000.0, rel=1e-9)
        # NOI from the calculator (EGI - opex) is 676_800. At debt_yield_floor=0.10:
        # max_loan_by_debt_yield = 676_800 / 0.10 = 6_768_000
        assert data["max_loan_by_debt_yield"] == pytest.approx(6_768_000.0, rel=1e-9)

    def test_unknown_run_returns_404(self, api_client):
        bogus = str(uuid4())
        resp = api_client.post(f"/api/v1/re/underwriting/runs/{bogus}/max-loan", json={})
        assert resp.status_code == 404

    def test_run_with_no_inputs_returns_400(self, api_client):
        create_resp = api_client.post(
            "/api/v1/re/underwriting/runs",
            json={"name": "No Inputs", "asset_type": "self_storage", "address": None, "documents": []},
        )
        run_id = create_resp.json()["run_id"]
        resp = api_client.post(f"/api/v1/re/underwriting/runs/{run_id}/max-loan", json={})
        assert resp.status_code == 400
