"""
Pydantic v2 schemas for the Self Storage underwriting wizard.

Covers the 6 wizard input steps (ProjectDetails → InvestmentCriteria),
the full SelfStorageInputs aggregate, and all calculator output models
(SelfStorageResult, VerdictResult, etc.).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, ConfigDict, model_validator


# ── INPUTS ───────────────────────────────────────────────────────────────────


class ProjectDetails(BaseModel):
    """Step 1 — basic property information."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    asset_type: str = "self_storage"
    address: Optional[str] = None
    num_units: Optional[int] = Field(
        default=None, description="Total rentable units / spaces."
    )
    rentable_sqft: Optional[float] = Field(
        default=None, description="Total rentable square footage."
    )
    year_built: Optional[int] = None
    nearby_storage_count_1mi: Optional[int] = Field(
        default=None,
        description="Number of nearby storage facilities within 1 mile.",
    )
    nearby_storage_count_3mi: Optional[int] = Field(
        default=None,
        description="Number of nearby storage facilities within 3 miles.",
    )
    nearby_storage_count_5mi: Optional[int] = Field(
        default=None,
        description="Number of nearby storage facilities within 5 miles.",
    )
    population_3mi: Optional[int] = Field(
        default=None,
        description="Population within a 3-mile radius.",
    )
    avg_household_income_3mi: Optional[float] = Field(
        default=None,
        description="Average household income within a 3-mile radius.",
    )
    storage_sqft_per_capita_3mi: Optional[float] = Field(
        default=None,
        description="Self-storage square feet per capita in the market.",
    )


class AcquisitionInputs(BaseModel):
    """Step 2 — purchase economics."""

    model_config = ConfigDict(populate_by_name=True)

    purchase_price: Optional[float] = Field(
        default=None,
        description="Asking / negotiated price.",
    )
    closing_cost_pct: float = Field(
        default=0.02, description="Closing costs as % of purchase price."
    )
    market_cap_rate_purchase: Optional[float] = Field(
        default=None,
        description="Market or broker-stated cap rate at the acquisition basis.",
    )
    capex_reserve_per_unit: float = Field(
        default=0.0, description="Upfront cap-ex reserve per unit."
    )


class OperationalInputs(BaseModel):
    """Step 3 — income & expense buildup (NOI)."""

    model_config = ConfigDict(populate_by_name=True)

    # Income
    gross_potential_rent_annual: float = Field(
        description="GPR: total rent if 100 % occupied at current rates."
    )
    avg_in_place_rent_per_unit_monthly: Optional[float] = Field(
        default=None,
        description="Average current monthly rent per unit / door.",
    )
    avg_market_rent_per_unit_monthly: Optional[float] = Field(
        default=None,
        description="Average market monthly rent per unit / door.",
    )
    vacancy_credit_loss_pct: float = Field(
        default=0.10, description="Vacancy + credit loss as % of GPR."
    )
    expense_ratio_current: Optional[float] = Field(
        default=None,
        description="Actual operating expense ratio as a decimal.",
    )
    expense_ratio_pro_forma: Optional[float] = Field(
        default=None,
        description="Pro forma operating expense ratio as a decimal.",
    )
    other_income_annual: float = Field(
        default=0.0, description="Late fees, admin, retail, etc."
    )
    noi_year_one_stated: Optional[float] = Field(
        default=None,
        description="Stated Year-1 NOI from OM operating statement — used for source vs computed reconciliation.",
    )
    noi_current_stated: Optional[float] = Field(
        default=None,
        description="Stated current NOI from OM operating statement — used for source vs computed reconciliation.",
    )
    income_basis_months: Optional[int] = Field(
        default=None,
        description="Period of the income statement used as the source (12 = T-12, 6 = T-6 annualized).",
    )
    income_basis_note: Optional[str] = Field(
        default=None,
        description="Analyst-facing note about income statement basis from the source document.",
    )
    bad_debt_annual: Optional[float] = Field(
        default=None,
        description="Annual bad debt or charge-offs when stated.",
    )
    corrections_collections_annual: Optional[float] = Field(
        default=None,
        description="Annual corrections / collections adjustments when stated.",
    )
    rent_growth_pct: float = Field(
        default=0.03, description="Annual rent growth rate."
    )

    # Expenses (annual)
    property_tax_annual: float = 0.0
    insurance_annual: float = 0.0
    mgmt_fee_pct: float = Field(
        default=0.08, description="Management fee as % of EGI."
    )
    payroll_annual: float = 0.0
    repairs_maintenance_annual: float = 0.0
    utilities_annual: float = 0.0
    marketing_annual: float = 0.0
    other_opex_annual: float = 0.0
    property_tax_growth_pct: Optional[float] = Field(
        default=None,
        description="Annual property tax growth rate.",
    )
    property_tax_value_basis_amount: Optional[float] = Field(
        default=None,
        description="Explicit value basis used for property tax calculation.",
    )
    property_tax_assessed_value: Optional[float] = Field(
        default=None,
        description="Explicit assessed or taxable assessed value for property tax calculation.",
    )
    property_tax_assessment_ratio: Optional[float] = Field(
        default=None,
        description="Property tax assessment ratio as a decimal.",
    )
    property_tax_millage_rate: Optional[float] = Field(
        default=None,
        description="Property tax millage rate in true mills per $1,000 of assessed value.",
    )
    property_tax_rate_per_assessed_dollar: Optional[float] = Field(
        default=None,
        description="Property tax rate per $1 of assessed value.",
    )
    opex_growth_pct: float = Field(
        default=0.02, description="Annual operating expense growth rate."
    )


class FinancingInputs(BaseModel):
    """Step 4 — debt structure."""

    model_config = ConfigDict(populate_by_name=True)

    ltv_pct: float = Field(default=0.70, description="Loan-to-value ratio.")
    interest_rate_pct: float = Field(
        default=0.065, description="Annual interest rate."
    )
    amortization_years: int = 25
    loan_term_years: int = 10


class ExitInputs(BaseModel):
    """Step 5 — disposition assumptions."""

    model_config = ConfigDict(populate_by_name=True)

    hold_period_years: int = Field(
        default=10, description="Investment hold period in years."
    )
    market_cap_rate_sale: Optional[float] = Field(
        default=None,
        description="Market cap rate benchmark for sale / exit basis.",
    )
    exit_cap_rate: float = Field(
        default=0.065, description="Cap rate applied at sale."
    )
    selling_cost_pct: float = Field(
        default=0.03,
        description="Broker commission + transfer taxes at exit.",
    )


class InvestmentCriteria(BaseModel):
    """Step 6 — per-deal return thresholds for the verdict engine."""

    model_config = ConfigDict(populate_by_name=True)

    target_irr: float = Field(
        default=0.15, description="Target IRR, e.g. 0.15 = 15 %."
    )
    target_cash_on_cash: float = Field(
        default=0.08, description="Target cash-on-cash, e.g. 0.08 = 8 %."
    )
    target_equity_multiple: float = 2.0
    max_ltv: float = Field(
        default=0.80, description="Hard upper bound on LTV."
    )


class UnitMixRow(BaseModel):
    """One row from a self-storage unit-mix schedule."""

    size: Optional[str] = Field(
        default=None,
        description='Unit size label such as "10 x 10".',
    )
    standard_sqft: Optional[float] = None
    num_units: Optional[int] = None
    occupied_units: Optional[int] = None
    occupancy_pct: Optional[float] = Field(
        default=None,
        description="Occupied units / total units as a decimal.",
    )
    current_rent: Optional[float] = Field(
        default=None,
        description="Current or in-place monthly asking/rack rate for this row when stated.",
    )
    market_rent: Optional[float] = Field(
        default=None,
        description="Market monthly rate when explicitly stated separately from current rate.",
    )
    rent_per_sqft: Optional[float] = None
    potential_rent: Optional[float] = Field(
        default=None,
        description="Potential monthly rent for the row when stated in the source table.",
    )
    occupied_sqft: Optional[float] = None
    total_sqft: Optional[float] = None
    pct_of_total_sqft: Optional[float] = Field(
        default=None,
        description="Share of total square footage represented by the row as a decimal.",
    )
    climate_type: Optional[Literal["CC", "NC", "UNKNOWN"]] = Field(
        default=None,
        description='"CC" = climate-controlled, "NC" = non-climate / drive-up, "UNKNOWN" = unclear.',
    )
    unit_category: Optional[Literal["storage", "parking", "residential", "office", "other"]] = Field(
        default=None,
        description='"storage" for standard units; "parking" for spaces; "residential" or "office" for non-storage.',
    )


class RentCompRow(BaseModel):
    """One nearby rent comp row for a self-storage competitive set."""

    facility: Optional[str] = Field(
        default=None,
        description="Nearby operator or facility name, such as U-Haul.",
    )
    size: Optional[str] = Field(
        default=None,
        description='Unit size label such as "5 x 10".',
    )
    asking_rent: Optional[float] = Field(
        default=None,
        description="Monthly asking rent per unit for the size bucket when stated.",
    )
    rent_per_sqft: Optional[float] = Field(
        default=None,
        description="Monthly asking rent per square foot for the size bucket when stated.",
    )
    distance_mi: Optional[float] = Field(
        default=None,
        description="Distance from the subject property in miles when stated.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional note such as online special or missing data.",
    )
    climate_type: Optional[Literal["CC", "NC", "UNKNOWN"]] = Field(
        default=None,
        description='"CC" = climate-controlled, "NC" = non-climate / drive-up, "UNKNOWN" = unclear.',
    )
    standard_sqft: Optional[float] = Field(
        default=None,
        description="Canonical unit area in sqft derived from the size string (e.g. '5×10' → 50).",
    )


class SelfStorageInputs(BaseModel):
    """Complete wizard inputs — one instance per underwriting run."""

    model_config = ConfigDict(populate_by_name=True)

    project: ProjectDetails
    acquisition: AcquisitionInputs
    operational: OperationalInputs
    financing: FinancingInputs
    exit: ExitInputs
    criteria: InvestmentCriteria
    lease_records: list[LeaseRecord] = Field(
        default_factory=list,
        description="Lease records from rent roll — used for rollover risk.",
    )
    unit_mix: list[UnitMixRow] = Field(
        default_factory=list,
        description="Best available unit-mix rows, typically from OM during early screening.",
    )
    rent_comps: list[RentCompRow] = Field(
        default_factory=list,
        description="Nearby self-storage rent comps from OM tables or manual analyst entry.",
    )


# ── OUTPUTS ──────────────────────────────────────────────────────────────────


class AnnualProjection(BaseModel):
    """One year of the hold-period pro-forma projection."""

    year: int
    gpr: float
    vacancy_loss: float
    other_income: float
    egi: float
    opex: float
    noi: float
    debt_service: float
    cash_flow: float
    principal_paydown: float
    property_value: float = Field(
        description="Estimated at current year's NOI / exit_cap_rate."
    )
    net_worth_increase: float = Field(
        description="cash_flow + principal_paydown + appreciation."
    )


class ExpenseBasis(BaseModel):
    """How operating expenses were modeled for the projection."""

    source: Literal[
        "line_items",
        "expense_ratio_current",
        "expense_ratio_pro_forma",
        "om_noi",
        "missing",
    ]
    label: str
    ratio: Optional[float] = None
    year1_line_item_opex: Optional[float] = None
    year1_ratio_opex: Optional[float] = None
    reason: str


class CapitalStructure(BaseModel):
    """Summary of the deal's capital stack at acquisition."""

    purchase_price: float
    down_payment: float
    loan_amount: float
    closing_cost: float
    capex_reserve_initial: float
    total_equity_invested: float = Field(
        description="down_payment + closing_cost + capex_reserve_initial."
    )


class TotalReturn(BaseModel):
    """Aggregate return figures across the full hold period."""

    annual_cash_flows_sum: float
    net_sale_price: float
    loan_balance_at_exit: float
    total_cash_received: float = Field(
        description="annual_cash_flows_sum + net_sale_price."
    )
    total_cash_invested: float = Field(
        description="Negative of total_equity_invested."
    )
    total_profit: float


class SensitivityPoint(BaseModel):
    """One point on the purchase-price sensitivity curve."""

    purchase_price: float
    irr: float
    cash_on_cash: float
    dscr_year_one: float
    equity_multiple: float


class StressScenario(BaseModel):
    """Result of a single stress-test scenario."""

    scenario_key: str = Field(
        description='Machine key, e.g. "vacancy_plus_500bps".'
    )
    label: str = Field(description="Human-readable scenario label.")
    irr: Optional[float] = None
    cash_on_cash: Optional[float] = None
    dscr_year_one: Optional[float] = None
    equity_multiple: Optional[float] = None
    min_dscr: Optional[float] = Field(
        default=None,
        description="Lowest DSCR across any projection year (loan covenant monitor).",
    )


class RolloverRisk(BaseModel):
    """Lease rollover / concentration risk metrics derived from the rent roll."""

    pct_rent_expiring_12mo: float
    pct_rent_expiring_24mo: float
    pct_rent_expiring_36mo: float
    top_5_tenants_pct: Optional[float] = None
    avg_remaining_term_months: Optional[float] = None


class VerdictFailure(BaseModel):
    """A single criterion that failed the investment threshold check."""

    metric: str
    target: float
    actual: Optional[float] = None
    gap: Optional[float] = None


class VerdictWarning(BaseModel):
    """A non-fatal warning that affects confidence or interpretation."""

    key: str
    message: str
    severity: str = Field(
        default="warning",
        description='"critical" | "warning" | "info".',
    )


class RentPositionRow(BaseModel):
    """Subject rent position versus the matched comp set for one size bucket."""

    size: str
    climate_type: str = Field(
        description='"NC" | "CC".',
    )
    subject_current_rent: Optional[float] = None
    subject_market_rent: Optional[float] = None
    comp_average_rent: float
    current_vs_comp_ratio: Optional[float] = None
    market_vs_comp_ratio: Optional[float] = None
    comp_count: int
    bucket: Optional[Literal["locker", "small", "medium", "large", "xlarge"]] = Field(
        default=None,
        description="Size bucket label: locker / small / medium / large / xlarge.",
    )


class FormulaComputedValues(BaseModel):
    """Numeric values that went into producing a metric — for tooltip display."""

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _round_floats(cls, data: dict) -> dict:
        return {k: round(v, 3) if isinstance(v, float) else v for k, v in data.items()}


class FormulaMetadata(BaseModel):
    """Formula description and computed inputs for a single metric."""

    description: str = Field(
        description="Human-readable formula definition and explanation."
    )
    computed_values: FormulaComputedValues = Field(
        default_factory=FormulaComputedValues,
        description="Key numeric values used to compute this metric (e.g., entry_equity, annual_debt_service).",
    )


class SelfStorageResult(BaseModel):
    """Full output from the underwriting calculator."""

    # Income basis provenance — populated from merged inputs, used by UI for T-6 badge
    income_basis_months: Optional[int] = Field(
        default=None,
        description="Period of the income statement used (12 = T-12, 6 = T-6 annualized).",
    )
    income_basis_note: Optional[str] = Field(
        default=None,
        description="Analyst-facing note about income statement basis, e.g. from the OM.",
    )

    # Formula metadata — backend-driven tooltips
    formula_metadata: dict[str, FormulaMetadata] = Field(
        default_factory=dict,
        description="Per-metric formula descriptions and computed inputs, keyed by metric name.",
    )

    # Top-line metrics
    irr: Optional[float] = None
    cash_on_cash: Optional[float] = Field(
        default=None, description="Year-1 cash-on-cash return."
    )
    equity_multiple: Optional[float] = None
    total_profit: Optional[float] = None
    cap_rate_year_one: Optional[float] = None
    cap_rate_pro_forma: Optional[float] = Field(
        default=None,
        description="Stabilised NOI / purchase price.",
    )
    dscr_year_one: Optional[float] = None
    break_even_occupancy_pct: Optional[float] = Field(
        default=None,
        description="Approximate occupancy needed for year-one NOI to cover debt service.",
    )
    ltv: Optional[float] = None
    noi_year_one: Optional[float] = None
    monthly_cashflow: Optional[float] = Field(
        default=None, description="Year-1 cash_flow / 12."
    )
    expense_basis: ExpenseBasis = Field(
        default_factory=lambda: ExpenseBasis(
            source="missing",
            label="Missing expense support",
            reason="No operating expense basis was available.",
        ),
        description="Explains whether OpEx came from line items or an expense-ratio fallback.",
    )

    # Detailed outputs
    capital_structure: CapitalStructure
    total_return: TotalReturn
    projections: list[AnnualProjection] = Field(
        default_factory=list,
        description="One entry per year of the hold period.",
    )
    sensitivity_curve: list[SensitivityPoint] = Field(
        default_factory=list,
        description="Populated on demand.",
    )
    stress_tests: list[StressScenario] = Field(
        default_factory=list,
        description="4 stress scenarios + base case.",
    )
    rollover_risk: Optional[RolloverRisk] = Field(
        default=None,
        description="Populated from rent-roll extraction.",
    )
    unit_mix: list[UnitMixRow] = Field(
        default_factory=list,
        description="Best available unit-mix evidence shown on the result page.",
    )
    rent_position_analysis: list[RentPositionRow] = Field(
        default_factory=list,
        description="Subject rent position versus matched extracted rent comps.",
    )
    unknown_climate_comp_count: int = Field(
        default=0,
        description="Number of rent comps excluded from matching because climate type was unclear.",
    )


class VerdictResult(BaseModel):
    """Go / no-go verdict produced by the threshold engine."""

    status: str = Field(
        description='"worth_pursuing" | "needs_review" | "below_standards".'
    )
    failures: list[VerdictFailure] = Field(default_factory=list)
    warnings: list[VerdictWarning] = Field(default_factory=list)
    rationale: str


# ── RENT ROLL (used by extraction → rollover risk) ────────────────────────────


class LeaseRecord(BaseModel):
    """A single lease entry parsed from the uploaded rent roll."""

    unit_id: Optional[str] = None
    tenant_name: Optional[str] = None
    monthly_rent: float
    lease_expiration: Optional[str] = Field(
        default=None,
        description='ISO date string, e.g. "2026-09-30".',
    )
    sqft: Optional[float] = None
