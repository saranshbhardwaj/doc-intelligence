"""Per-document extraction schemas for RE underwriting.

Each doc type gets its own typed schema. All fields Optional — a doc may
not contain every field. The merger maps these into SelfStorageInputs.

All three extraction models (OM, T-12, Rent Roll) are the single sources of
truth for their field registries. Add `Field(description=...,
json_schema_extra={"cite": bool})` to each scalar field and the LLM tool
schema, cited-field list, and prompt schema are all derived automatically via
the corresponding `_*_REGISTRY`.
"""

from __future__ import annotations

from typing import Optional, get_args
from pydantic import BaseModel, Field

from ..schemas.self_storage import LeaseRecord, RentCompRow, UnitMixRow

# Fields whose values are lists of nested models — excluded from scalar derivation
_OM_COMPLEX_FIELD_NAMES: frozenset[str] = frozenset({"unit_mix", "rent_comps"})
_T12_COMPLEX_FIELD_NAMES: frozenset[str] = frozenset()
_RENT_ROLL_COMPLEX_FIELD_NAMES: frozenset[str] = frozenset({"unit_mix", "lease_records"})


class OMExtraction(BaseModel):
    """Structured data extracted from an Offering Memorandum.

    Every scalar field carries:
      - description: used in the LLM tool schema and Phase-2 prompt schema
      - json_schema_extra={"cite": True/False}: True → field gets citation companions
        (_confidence, _citations, _source) in the Anthropic tool call output

    Add Field(description=..., json_schema_extra={"cite": bool}) to new fields
    and they are automatically included in the LLM schema, cited-field list,
    and om_source_data artifact — no other files need updating.
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    name:    Optional[str]   = Field(default=None, description="property name",    json_schema_extra={"cite": False})
    address: Optional[str]   = Field(default=None, description="property address", json_schema_extra={"cite": False})

    # ── Acquisition ───────────────────────────────────────────────────────────
    purchase_price:           Optional[float] = Field(default=None, description="asking or listing price",       json_schema_extra={"cite": True})
    closing_cost_pct:         Optional[float] = Field(default=None, description="decimal e.g. 0.02",             json_schema_extra={"cite": True})
    capex_reserve_per_unit:   Optional[float] = Field(default=None, description="capex reserve per unit",        json_schema_extra={"cite": True})
    market_cap_rate_purchase: Optional[float] = Field(default=None, description="decimal e.g. 0.0625",          json_schema_extra={"cite": True})

    # ── Property ──────────────────────────────────────────────────────────────
    num_units:      Optional[int]   = Field(default=None, description="total unit count",        json_schema_extra={"cite": True})
    rentable_sqft:  Optional[float] = Field(default=None, description="total rentable square feet", json_schema_extra={"cite": True})
    year_built:     Optional[int]   = Field(default=None, description="year property was built", json_schema_extra={"cite": False})

    # ── Market / Demographics ─────────────────────────────────────────────────
    nearby_storage_count_1mi:    Optional[int]   = Field(default=None, description="competing storage facilities within 1 mile",  json_schema_extra={"cite": True})
    nearby_storage_count_3mi:    Optional[int]   = Field(default=None, description="competing storage facilities within 3 miles", json_schema_extra={"cite": True})
    nearby_storage_count_5mi:    Optional[int]   = Field(default=None, description="competing storage facilities within 5 miles", json_schema_extra={"cite": True})
    population_3mi:              Optional[int]   = Field(default=None, description="population within 3-mile radius",             json_schema_extra={"cite": True})
    avg_household_income_3mi:    Optional[float] = Field(default=None, description="average household income within 3 miles",     json_schema_extra={"cite": True})
    storage_sqft_per_capita_3mi: Optional[float] = Field(default=None, description="storage sqft per capita within 3 miles",     json_schema_extra={"cite": True})

    # ── Income ────────────────────────────────────────────────────────────────
    gpr_annual_projected:                Optional[float] = Field(default=None, description="annual gross potential rent",                   json_schema_extra={"cite": True})
    avg_in_place_rent_per_unit_monthly:  Optional[float] = Field(default=None, description="average monthly in-place rent per unit",        json_schema_extra={"cite": True})
    avg_market_rent_per_unit_monthly:    Optional[float] = Field(default=None, description="average monthly market rent per unit",          json_schema_extra={"cite": True})
    vacancy_pct_projected:               Optional[float] = Field(default=None, description="decimal e.g. 0.1278 — Year 1 economic vacancy", json_schema_extra={"cite": True})
    other_income_annual:                 Optional[float] = Field(default=None, description="annual total of all non-rental income Year 1",  json_schema_extra={"cite": True})
    rent_growth_pct:                     Optional[float] = Field(default=None, description="decimal e.g. 0.03",                             json_schema_extra={"cite": True})

    # Individual other-income components — fallback aggregation when other_income_annual is missed
    other_income_admin_fees_annual:  Optional[float] = Field(default=None, description="Administrative Fees Year 1",                json_schema_extra={"cite": True})
    other_income_late_fees_annual:   Optional[float] = Field(default=None, description="Late/Lien/NSF Fees Year 1",                 json_schema_extra={"cite": True})
    other_income_insurance_annual:   Optional[float] = Field(default=None, description="Tenant Insurance Net Commissions Year 1",   json_schema_extra={"cite": True})
    other_income_misc_annual:        Optional[float] = Field(default=None, description="Miscellaneous Income Year 1",               json_schema_extra={"cite": True})

    # ── Operations ────────────────────────────────────────────────────────────
    noi_projected:         Optional[float] = Field(default=None, description="projected net operating income",     json_schema_extra={"cite": True})
    mgmt_fee_pct:          Optional[float] = Field(default=None, description="decimal e.g. 0.08",                  json_schema_extra={"cite": True})
    opex_growth_pct:       Optional[float] = Field(default=None, description="decimal e.g. 0.02",                  json_schema_extra={"cite": True})
    property_tax_growth_pct: Optional[float] = Field(default=None, description="decimal e.g. 0.04",               json_schema_extra={"cite": True})
    mil_rate:              Optional[float] = Field(default=None, description="property tax mill rate",             json_schema_extra={"cite": True})
    expense_ratio_pro_forma: Optional[float] = Field(default=None, description="decimal e.g. 0.35",               json_schema_extra={"cite": True})

    # ── Individual expense line items (Year 1 column preferred) ───────────────
    expense_office_admin_annual:        Optional[float] = Field(default=None, description="Office & Admin annual, Year 1 column preferred",  json_schema_extra={"cite": True})
    expense_bank_fees_annual:           Optional[float] = Field(default=None, description="Bank & Credit Card Fees annual",                  json_schema_extra={"cite": True})
    expense_contract_services_annual:   Optional[float] = Field(default=None, description="Contract Services annual",                        json_schema_extra={"cite": True})
    expense_miscellaneous_annual:       Optional[float] = Field(default=None, description="Miscellaneous annual",                            json_schema_extra={"cite": True})
    expense_utilities_annual:           Optional[float] = Field(default=None, description="Utilities & Trash annual",                        json_schema_extra={"cite": True})
    expense_telephone_annual:           Optional[float] = Field(default=None, description="Telephone & Communications annual",               json_schema_extra={"cite": True})
    expense_marketing_annual:           Optional[float] = Field(default=None, description="Marketing & Promotion annual",                    json_schema_extra={"cite": True})
    expense_repairs_maintenance_annual: Optional[float] = Field(default=None, description="Repairs, Maintenance & Reserves annual",          json_schema_extra={"cite": True})
    expense_insurance_annual:           Optional[float] = Field(default=None, description="Property Insurance annual",                       json_schema_extra={"cite": True})
    expense_payroll_annual:             Optional[float] = Field(default=None, description="Salaries, Taxes & Benefits annual",               json_schema_extra={"cite": True})
    expense_property_tax_annual:        Optional[float] = Field(default=None, description="Property Taxes annual",                           json_schema_extra={"cite": True})
    expense_mgmt_fee_annual:            Optional[float] = Field(default=None, description="Third Party Management annual",                   json_schema_extra={"cite": False})
    expense_total_annual:               Optional[float] = Field(default=None, description="Total Operating Expenses annual",                 json_schema_extra={"cite": False})
    noi_year_one_stated:                Optional[float] = Field(default=None, description="NOI from Year 1 column",                         json_schema_extra={"cite": False})
    noi_current_stated:                 Optional[float] = Field(default=None, description="NOI from Current column",                        json_schema_extra={"cite": False})

    # ── Financing & Exit ──────────────────────────────────────────────────────
    ltv_pct:             Optional[float] = Field(default=None, description="decimal e.g. 0.70",      json_schema_extra={"cite": True})
    interest_rate_pct:   Optional[float] = Field(default=None, description="decimal e.g. 0.065",     json_schema_extra={"cite": True})
    amortization_years:  Optional[int]   = Field(default=None, description="loan amortization years", json_schema_extra={"cite": True})
    loan_term_years:     Optional[int]   = Field(default=None, description="loan term years",         json_schema_extra={"cite": True})
    exit_cap_rate:       Optional[float] = Field(default=None, description="decimal e.g. 0.065",      json_schema_extra={"cite": True})
    market_cap_rate_sale: Optional[float] = Field(default=None, description="decimal e.g. 0.0675",   json_schema_extra={"cite": True})
    hold_period_years:   Optional[int]   = Field(default=None, description="investment hold period",  json_schema_extra={"cite": True})
    selling_cost_pct:    Optional[float] = Field(default=None, description="decimal e.g. 0.03",       json_schema_extra={"cite": True})

    # ── Investment Criteria (when stated in OM) ───────────────────────────────
    target_irr:             Optional[float] = Field(default=None, description="decimal e.g. 0.15", json_schema_extra={"cite": True})
    target_cash_on_cash:    Optional[float] = Field(default=None, description="decimal",           json_schema_extra={"cite": True})
    target_equity_multiple: Optional[float] = Field(default=None, description="equity multiple",   json_schema_extra={"cite": True})

    # ── Value-Add Evidence ────────────────────────────────────────────────────
    income_basis_months:         Optional[int]   = Field(default=None, description="6 or 12, when income period is stated",        json_schema_extra={"cite": True})
    income_basis_note:           Optional[str]   = Field(default=None, description="explanation of income period",                 json_schema_extra={"cite": False})
    physical_occupancy_pct:      Optional[float] = Field(default=None, description="decimal, stated occupancy e.g. 0.91",          json_schema_extra={"cite": True})
    price_per_rentable_sqft:     Optional[float] = Field(default=None, description="stated price per sqft if present",             json_schema_extra={"cite": False})
    below_market_tenant_pct:     Optional[float] = Field(default=None, description="decimal, e.g. 0.36 for 36%",                  json_schema_extra={"cite": True})
    below_market_monthly_variance: Optional[float] = Field(default=None, description="total monthly rent gap in dollars",         json_schema_extra={"cite": True})
    below_market_annual_upside:  Optional[float] = Field(default=None, description="annual dollar upside from below-market tenants", json_schema_extra={"cite": True})
    value_add_notes:             Optional[str]   = Field(default=None, description="free text expansion or value-add narrative",   json_schema_extra={"cite": True})

    # ── Complex types (not scalar — excluded from registry derivation) ─────────
    unit_mix:   list[UnitMixRow]  = Field(default_factory=list)
    rent_comps: list[RentCompRow] = Field(default_factory=list)


def om_field_registry() -> dict:
    """Derive field lists and schemas from OMExtraction metadata.

    Returns a dict with four keys:
      scalar_fields        — list[str] of all non-complex field names
      cited_scalar_fields  — list[str] of fields with cite=True
      om_fields_for_prompt — list[{name, type}] for Phase 2 prompt _schema_json()
      om_schema_for_tool   — dict[name, {type, ?description}] for Anthropic tool schema
    """
    scalar_fields: list[str] = []
    cited_scalar_fields: list[str] = []
    om_fields_for_prompt: list[dict] = []
    om_schema_for_tool: dict = {}

    for field_name, field_info in OMExtraction.model_fields.items():
        if field_name in _OM_COMPLEX_FIELD_NAMES:
            continue

        annotation = field_info.annotation
        args = get_args(annotation)
        py_type = next((a for a in args if a is not type(None)), annotation)

        if py_type is str:
            json_type = "string"
            prompt_type = "str | null"
        elif py_type is int:
            json_type = "integer"
            prompt_type = "int | null"
        else:
            json_type = "number"
            prompt_type = "float | null"

        description: str = field_info.description or ""
        extra: dict = field_info.json_schema_extra or {}

        scalar_fields.append(field_name)
        if extra.get("cite"):
            cited_scalar_fields.append(field_name)

        prompt_type_str = f"{prompt_type} ({description})" if description else prompt_type
        om_fields_for_prompt.append({"name": field_name, "type": prompt_type_str})

        schema_entry: dict = {"type": json_type}
        if description:
            schema_entry["description"] = description
        om_schema_for_tool[field_name] = schema_entry

    return {
        "scalar_fields": scalar_fields,
        "cited_scalar_fields": cited_scalar_fields,
        "om_fields_for_prompt": om_fields_for_prompt,
        "om_schema_for_tool": om_schema_for_tool,
    }


# Computed once at import time — zero runtime overhead per extraction call
_OM_REGISTRY: dict = om_field_registry()


class T12Extraction(BaseModel):
    """Structured data extracted from a T-12 or T-6 operating statement.

    Every scalar field carries:
      - description: used in the LLM tool schema and Phase-2 prompt schema
      - json_schema_extra={"cite": True/False}: True → field gets citation companions

    Add Field(description=..., json_schema_extra={"cite": bool}) to new fields
    and they are automatically included in the schema, cited-field list, and
    prompt — no other files need updating.
    """

    gpr_annual_actual:               Optional[float] = Field(default=None, description="Gross Potential Rent for the statement period",           json_schema_extra={"cite": True})
    vacancy_credit_loss_pct_actual:  Optional[float] = Field(default=None, description="vacancy / credit loss as decimal e.g. 0.08",              json_schema_extra={"cite": True})
    expense_ratio_actual:            Optional[float] = Field(default=None, description="total expenses / EGI as decimal",                          json_schema_extra={"cite": True})
    other_income_annual:             Optional[float] = Field(default=None, description="all non-rental income for the period",                     json_schema_extra={"cite": True})
    bad_debt_annual:                 Optional[float] = Field(default=None, description="bad debt write-offs for the period",                       json_schema_extra={"cite": True})
    corrections_collections_annual:  Optional[float] = Field(default=None, description="collections or prior-period adjustments",                  json_schema_extra={"cite": True})
    property_tax_annual:             Optional[float] = Field(default=None, description="property taxes for the period",                            json_schema_extra={"cite": True})
    insurance_annual:                Optional[float] = Field(default=None, description="property insurance for the period",                        json_schema_extra={"cite": True})
    mgmt_fee_pct_actual:             Optional[float] = Field(default=None, description="management fee percentage as decimal e.g. 0.08",           json_schema_extra={"cite": True})
    payroll_annual:                  Optional[float] = Field(default=None, description="payroll and benefits for the period",                      json_schema_extra={"cite": True})
    repairs_maintenance_annual:      Optional[float] = Field(default=None, description="repairs and maintenance for the period",                   json_schema_extra={"cite": True})
    utilities_annual:                Optional[float] = Field(default=None, description="utilities for the period",                                 json_schema_extra={"cite": True})
    marketing_annual:                Optional[float] = Field(default=None, description="marketing and advertising for the period",                 json_schema_extra={"cite": True})
    other_opex_annual:               Optional[float] = Field(default=None, description="all other operating expenses for the period",              json_schema_extra={"cite": False})
    noi_actual:                      Optional[float] = Field(default=None, description="net operating income for the period",                      json_schema_extra={"cite": True})
    period_months:                   Optional[int]   = Field(default=None, description="12 or 6 — used to annualise T-6 (× 12/period_months)",    json_schema_extra={"cite": False})


def t12_field_registry() -> dict:
    """Derive field lists and schemas from T12Extraction metadata.

    Returns same shape as om_field_registry() for consistency.
    """
    scalar_fields: list[str] = []
    cited_scalar_fields: list[str] = []
    t12_fields_for_prompt: list[dict] = []
    t12_schema_for_tool: dict = {}

    for field_name, field_info in T12Extraction.model_fields.items():
        if field_name in _T12_COMPLEX_FIELD_NAMES:
            continue

        annotation = field_info.annotation
        args = get_args(annotation)
        py_type = next((a for a in args if a is not type(None)), annotation)

        if py_type is str:
            json_type = "string"
            prompt_type = "str | null"
        elif py_type is int:
            json_type = "integer"
            prompt_type = "int | null"
        else:
            json_type = "number"
            prompt_type = "float | null"

        description: str = field_info.description or ""
        extra: dict = field_info.json_schema_extra or {}

        scalar_fields.append(field_name)
        if extra.get("cite"):
            cited_scalar_fields.append(field_name)

        prompt_type_str = f"{prompt_type} ({description})" if description else prompt_type
        t12_fields_for_prompt.append({"name": field_name, "type": prompt_type_str})

        schema_entry: dict = {"type": json_type}
        if description:
            schema_entry["description"] = description
        t12_schema_for_tool[field_name] = schema_entry

    return {
        "scalar_fields": scalar_fields,
        "cited_scalar_fields": cited_scalar_fields,
        "t12_fields_for_prompt": t12_fields_for_prompt,
        "t12_schema_for_tool": t12_schema_for_tool,
    }


_T12_REGISTRY: dict = t12_field_registry()


class RentRollExtraction(BaseModel):
    """Structured data extracted from a Rent Roll.

    Every scalar field carries:
      - description: used in the LLM tool schema and Phase-2 prompt schema
      - json_schema_extra={"cite": True/False}: True → field gets citation companions
    """

    num_units_actual:                 Optional[int]   = Field(default=None, description="total unit count including occupied and vacant",          json_schema_extra={"cite": True})
    physical_occupancy_pct:           Optional[float] = Field(default=None, description="occupied / total units as decimal e.g. 0.91",             json_schema_extra={"cite": True})
    avg_in_place_rent_per_unit_monthly: Optional[float] = Field(default=None, description="average monthly in-place rent per occupied unit",       json_schema_extra={"cite": True})
    avg_market_rent_per_unit_monthly: Optional[float] = Field(default=None, description="average monthly market rent per unit, null if no market column", json_schema_extra={"cite": False})
    rent_growth_pct:                  Optional[float] = Field(default=None, description="annual rent growth as decimal, only if explicitly stated", json_schema_extra={"cite": False})
    unit_mix:    list[UnitMixRow]   = Field(default_factory=list)
    lease_records: list[LeaseRecord] = Field(default_factory=list)


def rent_roll_field_registry() -> dict:
    """Derive field lists and schemas from RentRollExtraction metadata."""
    scalar_fields: list[str] = []
    cited_scalar_fields: list[str] = []
    rr_fields_for_prompt: list[dict] = []
    rr_schema_for_tool: dict = {}

    for field_name, field_info in RentRollExtraction.model_fields.items():
        if field_name in _RENT_ROLL_COMPLEX_FIELD_NAMES:
            continue

        annotation = field_info.annotation
        args = get_args(annotation)
        py_type = next((a for a in args if a is not type(None)), annotation)

        if py_type is str:
            json_type = "string"
            prompt_type = "str | null"
        elif py_type is int:
            json_type = "integer"
            prompt_type = "int | null"
        else:
            json_type = "number"
            prompt_type = "float | null"

        description: str = field_info.description or ""
        extra: dict = field_info.json_schema_extra or {}

        scalar_fields.append(field_name)
        if extra.get("cite"):
            cited_scalar_fields.append(field_name)

        prompt_type_str = f"{prompt_type} ({description})" if description else prompt_type
        rr_fields_for_prompt.append({"name": field_name, "type": prompt_type_str})

        schema_entry: dict = {"type": json_type}
        if description:
            schema_entry["description"] = description
        rr_schema_for_tool[field_name] = schema_entry

    return {
        "scalar_fields": scalar_fields,
        "cited_scalar_fields": cited_scalar_fields,
        "rr_fields_for_prompt": rr_fields_for_prompt,
        "rr_schema_for_tool": rr_schema_for_tool,
    }


_RENT_ROLL_REGISTRY: dict = rent_roll_field_registry()


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
    # "S{source_index}:p{page}" → {page, filename, document_id, source_index, bbox?}
    citation_context: dict = Field(default_factory=dict)
    extraction_metadata: dict = Field(default_factory=dict)
    error: Optional[str] = None  # set if optional doc extraction failed
