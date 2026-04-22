"""Per-document extraction schemas for RE underwriting.

Each doc type gets its own typed schema. All fields Optional — a doc may
not contain every field. The merger maps these into SelfStorageInputs.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

from ..schemas.self_storage import LeaseRecord


class OMExtraction(BaseModel):
    """Structured data extracted from an Offering Memorandum."""

    name: Optional[str] = None
    address: Optional[str] = None
    purchase_price: Optional[float] = None
    closing_cost_pct: Optional[float] = None
    capex_reserve_per_unit: Optional[float] = None
    num_units: Optional[int] = None
    rentable_sqft: Optional[float] = None
    year_built: Optional[int] = None
    gpr_annual_projected: Optional[float] = None
    vacancy_pct_projected: Optional[float] = None
    noi_projected: Optional[float] = None
    mgmt_fee_pct: Optional[float] = None
    exit_cap_rate: Optional[float] = None
    hold_period_years: Optional[int] = None
    selling_cost_pct: Optional[float] = None
    target_irr: Optional[float] = None
    target_cash_on_cash: Optional[float] = None
    target_equity_multiple: Optional[float] = None
    ltv_pct: Optional[float] = None
    interest_rate_pct: Optional[float] = None
    amortization_years: Optional[int] = None
    loan_term_years: Optional[int] = None


class T12Extraction(BaseModel):
    """Structured data extracted from a T-12 or T-6 operating statement."""

    gpr_annual_actual: Optional[float] = None
    vacancy_credit_loss_pct_actual: Optional[float] = None
    other_income_annual: Optional[float] = None
    property_tax_annual: Optional[float] = None
    insurance_annual: Optional[float] = None
    mgmt_fee_pct_actual: Optional[float] = None
    payroll_annual: Optional[float] = None
    repairs_maintenance_annual: Optional[float] = None
    utilities_annual: Optional[float] = None
    marketing_annual: Optional[float] = None
    other_opex_annual: Optional[float] = None
    noi_actual: Optional[float] = None
    period_months: Optional[int] = None  # 12 or 6 — used to annualise T-6 (× 12/period_months)


class RentRollExtraction(BaseModel):
    """Structured data extracted from a Rent Roll."""

    num_units_actual: Optional[int] = None
    physical_occupancy_pct: Optional[float] = None
    lease_records: list[LeaseRecord] = Field(default_factory=list)
    rent_growth_pct: Optional[float] = None


class CondensedField(BaseModel):
    """One financially relevant data point from a Phase 1 condensation batch."""

    field: str
    value: str
    citations: list[str] = Field(default_factory=list)
    source_text: str = ""


class CondensedBatchExtraction(BaseModel):
    """Output of one Phase 1 (map) LLM call over a batch of chunks."""

    fields: list[CondensedField] = Field(default_factory=list)


class ExtractedDocResult(BaseModel):
    """Result of extracting one document. Passed (as small JSON) to merge task."""

    run_id: str
    job_id: str
    doc_type: str  # "om" | "t12" | "rent_roll"
    om: Optional[OMExtraction] = None
    t12: Optional[T12Extraction] = None
    rent_roll: Optional[RentRollExtraction] = None
    field_citations: dict = Field(default_factory=dict)
    error: Optional[str] = None  # set if optional doc extraction failed
