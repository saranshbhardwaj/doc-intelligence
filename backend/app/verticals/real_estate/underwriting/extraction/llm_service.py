"""LLM service for Self Storage underwriting extraction."""
import json as _json
import time
from app.services.llm_client import LLMClient
from app.utils.logging import logger
from app.utils.metrics import (
    LLM_TOKEN_USAGE, LLM_CACHE_HITS, LLM_CACHE_MISSES,
    LLM_REQUESTS_TOTAL, LLM_COST_USD,
)
from app.utils.costs import compute_llm_cost
from .prompts import (
    OM_EXTRACTION_SYSTEM_PROMPT,
    RENT_ROLL_EXTRACTION_SYSTEM_PROMPT,
    T12_EXTRACTION_SYSTEM_PROMPT,
    create_om_user_prompt,
    create_rent_roll_user_prompt,
    create_t12_user_prompt,
    PHASE1_CONDENSATION_SYSTEM_PROMPT,
    create_phase1_user_prompt,
    create_phase2_om_prompt,
    create_phase2_t12_prompt,
    create_phase2_rent_roll_prompt,
)
from .rent_comp_repair import repair_om_rent_comp_rows
from .schemas import OMExtraction, T12Extraction, RentRollExtraction, CondensedBatchExtraction


class REExtractionLLMService:
    """LLM service for Real Estate extraction with Anthropic ephemeral caching."""

    def __init__(self, llm_client: LLMClient, run_id: str | None = None):
        self.llm_client = llm_client
        self.client = llm_client.client
        self.model = llm_client.model
        self.max_tokens = llm_client.max_tokens
        self.run_id = run_id or "unknown"
        logger.info(f"REExtractionLLMService initialized with model: {self.model}")

    def _record_llm_metrics(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_read: int,
        cache_write: int,
        stage: str,
    ) -> None:
        try:
            op = "re_underwriting"
            LLM_REQUESTS_TOTAL.labels(model=self.model, operation_type=op).inc()
            if input_tokens:
                LLM_TOKEN_USAGE.labels(model=self.model, token_type="input", operation_type=op).inc(input_tokens)
            if output_tokens:
                LLM_TOKEN_USAGE.labels(model=self.model, token_type="output", operation_type=op).inc(output_tokens)
            if cache_read:
                LLM_TOKEN_USAGE.labels(model=self.model, token_type="cache_read", operation_type=op).inc(cache_read)
                LLM_CACHE_HITS.labels(operation_type=op).inc()
            else:
                LLM_CACHE_MISSES.labels(operation_type=op).inc()
            if cache_write:
                LLM_TOKEN_USAGE.labels(model=self.model, token_type="cache_write", operation_type=op).inc(cache_write)
            if input_tokens and output_tokens:
                cost = compute_llm_cost(self.model, input_tokens, output_tokens)
                if cost:
                    LLM_COST_USD.labels(model=self.model, operation_type=op).inc(cost)
        except Exception as e:
            logger.warning(f"Failed to record RE underwriting LLM metrics ({stage}): {e}")

    def extract_om(self, document_text: str) -> dict:
        """Extract from Offering Memorandum. Returns {scalars, field_citations}."""
        return self._extract(
            system_prompt=OM_EXTRACTION_SYSTEM_PROMPT,
            user_prompt=create_om_user_prompt(document_text),
            doc_type="om",
            schema_cls=OMExtraction,
            source_context=document_text,
        )

    def extract_rent_roll(self, document_text: str) -> dict:
        """Extract from Rent Roll. Returns {scalars, field_citations}."""
        return self._extract(
            system_prompt=RENT_ROLL_EXTRACTION_SYSTEM_PROMPT,
            user_prompt=create_rent_roll_user_prompt(document_text),
            doc_type="rent_roll",
            schema_cls=RentRollExtraction,
        )

    def extract_t12(self, document_text: str) -> dict:
        """Extract from T12 operating statement. Returns {scalars, field_citations}."""
        return self._extract(
            system_prompt=T12_EXTRACTION_SYSTEM_PROMPT,
            user_prompt=create_t12_user_prompt(document_text),
            doc_type="t12",
            schema_cls=T12Extraction,
        )
    
    _OM_CITED_SCALAR_FIELDS = [
    "purchase_price", "market_cap_rate_purchase", "num_units", "rentable_sqft",
    "gpr_annual_projected", "avg_in_place_rent_per_unit_monthly",
    "avg_market_rent_per_unit_monthly", "vacancy_pct_projected",
    "expense_ratio_pro_forma", "other_income_annual", "rent_growth_pct",
    "expense_property_tax_annual", "property_tax_growth_pct", "mil_rate",
    "expense_insurance_annual", "mgmt_fee_pct", "expense_payroll_annual",
    "expense_repairs_maintenance_annual", "expense_utilities_annual",
    "expense_marketing_annual", "other_opex_annual", "opex_growth_pct",
    "nearby_storage_count_1mi", "nearby_storage_count_3mi",
    "population_3mi", "avg_household_income_3mi", "storage_sqft_per_capita_3mi",
    "interest_rate_pct", "ltv_pct", "amortization_years",
    "exit_cap_rate", "hold_period_years", "selling_cost_pct",
    "income_basis_months", "physical_occupancy_pct",
    "below_market_tenant_pct", "below_market_annual_upside",
    "noi_projected",
]

    # Flat tool schemas — no anyOf/null unions (Anthropic 16-union limit).
    # Each scalar field has three companion properties for first-class citations:
    #   {field}_confidence: float 0-1
    #   {field}_citations:  list of page tokens e.g. ["S1:p5"]
    #   {field}_source:     brief verbatim snippet
    # All fields non-required — model omits what it can't find.
    _OM_SCALAR_FIELDS = [
        "name", "address", "purchase_price", "closing_cost_pct", "capex_reserve_per_unit",
        "market_cap_rate_purchase", "num_units", "rentable_sqft", "year_built",
        "nearby_storage_count_1mi", "nearby_storage_count_3mi", "nearby_storage_count_5mi",
        "population_3mi", "avg_household_income_3mi", "storage_sqft_per_capita_3mi",
        "gpr_annual_projected", "avg_in_place_rent_per_unit_monthly",
        "avg_market_rent_per_unit_monthly", "vacancy_pct_projected", "expense_ratio_pro_forma",
        "other_income_annual", "rent_growth_pct", "noi_projected", "mgmt_fee_pct",
        "opex_growth_pct", "property_tax_growth_pct", "mil_rate", "exit_cap_rate",
        "market_cap_rate_sale", "hold_period_years", "selling_cost_pct", "target_irr",
        "target_cash_on_cash", "target_equity_multiple", "ltv_pct", "interest_rate_pct",
        "amortization_years", "loan_term_years",
        "income_basis_months", "income_basis_note",
        "physical_occupancy_pct", "price_per_rentable_sqft",
        "below_market_tenant_pct", "below_market_monthly_variance",
        "below_market_annual_upside", "value_add_notes", "noi_projected", "unit_mix", "rent_comps",
        # Individual expense line items — Year 1 column preferred
        "expense_office_admin_annual",
        "expense_bank_fees_annual",
        "expense_contract_services_annual",
        "expense_miscellaneous_annual",
        "expense_utilities_annual",
        "expense_telephone_annual",
        "expense_marketing_annual",
        "expense_repairs_maintenance_annual",
        "expense_insurance_annual",
        "expense_payroll_annual",
        "expense_property_tax_annual",
        "expense_mgmt_fee_annual",
        "expense_total_annual",
        "noi_year_one_stated",
        "noi_current_stated",

    ]
    _T12_SCALAR_FIELDS = [
        "gpr_annual_actual", "vacancy_credit_loss_pct_actual", "expense_ratio_actual",
        "other_income_annual", "bad_debt_annual", "corrections_collections_annual",
        "property_tax_annual", "insurance_annual", "mgmt_fee_pct_actual", "payroll_annual",
        "repairs_maintenance_annual", "utilities_annual", "marketing_annual",
        "other_opex_annual", "noi_actual", "period_months",
    ]
    _RENT_ROLL_SCALAR_FIELDS = [
        "num_units_actual", "physical_occupancy_pct", "avg_in_place_rent_per_unit_monthly",
        "avg_market_rent_per_unit_monthly", "rent_growth_pct",
    ]
    # unit_mix and rent_comps are tables — no per-collection citation companions needed
    _OM_CITED_COLLECTION_FIELDS: list = []
    _RENT_ROLL_CITED_COLLECTION_FIELDS: list = []

    @classmethod
    def _citation_props(cls, field: str) -> dict:
        return {
            f"{field}_confidence": {"type": "number", "description": "0.0-1.0 confidence"},
            f"{field}_citations":  {"type": "array", "items": {"type": "string"}, "description": 'page tokens e.g. ["S1:p5"]'},
            f"{field}_source":     {"type": "string", "description": "verbatim snippet ≤40 chars"},
        }

    @classmethod
    def _build_om_schema(cls) -> dict:
        base = {
            "name":                   {"type": "string"},
            "address":                {"type": "string"},
            "purchase_price":         {"type": "number"},
            "closing_cost_pct":       {"type": "number", "description": "decimal e.g. 0.02"},
            "capex_reserve_per_unit": {"type": "number"},
            "market_cap_rate_purchase": {"type": "number", "description": "decimal e.g. 0.0625"},
            "num_units":              {"type": "integer"},
            "rentable_sqft":          {"type": "number"},
            "year_built":             {"type": "integer"},
            "nearby_storage_count_1mi": {"type": "integer"},
            "nearby_storage_count_3mi": {"type": "integer"},
            "nearby_storage_count_5mi": {"type": "integer"},
            "population_3mi":         {"type": "integer"},
            "avg_household_income_3mi": {"type": "number"},
            "storage_sqft_per_capita_3mi": {"type": "number"},
            "gpr_annual_projected":   {"type": "number", "description": "annual gross potential rent"},
            "avg_in_place_rent_per_unit_monthly": {"type": "number"},
            "avg_market_rent_per_unit_monthly": {"type": "number"},
            "vacancy_pct_projected":  {"type": "number", "description": "decimal e.g. 0.08"},
            "expense_ratio_pro_forma": {"type": "number", "description": "decimal e.g. 0.35"},
            "other_income_annual":    {"type": "number"},
            "rent_growth_pct":        {"type": "number", "description": "decimal e.g. 0.03"},
            "noi_projected":          {"type": "number"},
            "mgmt_fee_pct":           {"type": "number", "description": "decimal e.g. 0.08"},
            "opex_growth_pct":        {"type": "number", "description": "decimal e.g. 0.02"},
            "property_tax_growth_pct": {"type": "number", "description": "decimal e.g. 0.04"},
            "mil_rate":               {"type": "number"},
            "exit_cap_rate":          {"type": "number", "description": "decimal e.g. 0.065"},
            "market_cap_rate_sale":   {"type": "number", "description": "decimal e.g. 0.0675"},
            "hold_period_years":      {"type": "integer"},
            "selling_cost_pct":       {"type": "number", "description": "decimal e.g. 0.03"},
            "target_irr":             {"type": "number", "description": "decimal e.g. 0.15"},
            "target_cash_on_cash":    {"type": "number", "description": "decimal"},
            "target_equity_multiple": {"type": "number"},
            "ltv_pct":                {"type": "number", "description": "decimal e.g. 0.70"},
            "interest_rate_pct":      {"type": "number", "description": "decimal e.g. 0.065"},
            "amortization_years":     {"type": "integer"},
            "loan_term_years":        {"type": "integer"},
            "unit_mix": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "section":          {"type": "string"},
                        "unit_type":        {"type": "string"},
                        "size":             {"type": "string"},
                        "standard_sqft":    {"type": "number"},
                        "num_units":        {"type": "integer"},
                        "occupied_units":   {"type": "integer"},
                        "occupancy_pct":    {"type": "number", "description": "decimal"},
                        "current_rent":     {"type": "number"},
                        "market_rent":      {"type": "number"},
                        "rent_per_sqft":    {"type": "number"},
                        "potential_rent":   {"type": "number"},
                        "occupied_sqft":    {"type": "number"},
                        "total_sqft":       {"type": "number"},
                        "pct_of_total_sqft": {"type": "number", "description": "decimal"},
                        "climate_type":     {"type": "string", "description": '"CC" | "NC" | "UNKNOWN"'},
                        "unit_category":    {"type": "string", "description": '"storage" | "parking" | "residential" | "office" | "other"'},
                    },
                },
            },
            "rent_comps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "facility": {"type": "string"},
                        "size": {"type": "string"},
                        "asking_rent": {"type": "number"},
                        "rent_per_sqft": {"type": "number"},
                        "distance_mi": {"type": "number"},
                        "notes": {"type": "string"},
                    },
                },
            },
            "income_basis_months":          {"type": "integer", "description": "6 or 12, when income period is stated"},
            "income_basis_note":            {"type": "string"},
            "physical_occupancy_pct":       {"type": "number", "description": "decimal, stated occupancy e.g. 0.91"},
            "price_per_rentable_sqft":      {"type": "number", "description": "stated price per sqft if present"},
            "below_market_tenant_pct":      {"type": "number", "description": "decimal, e.g. 0.36 for 36%"},
            "below_market_monthly_variance":{"type": "number", "description": "total monthly rent gap in dollars"},
            "below_market_annual_upside":   {"type": "number", "description": "annual dollar upside from below-market tenants"},
            "value_add_notes":              {"type": "string", "description": "free text expansion or value-add narrative"},
            "noi_projected":                {"type": "number", "description": "projected net operating income"},

            # Individual expense line items
            "expense_office_admin_annual":        {"type": "number", "description": "Office & Admin annual, Year 1 column preferred"},
            "expense_bank_fees_annual":           {"type": "number", "description": "Bank & Credit Card Fees annual"},
            "expense_contract_services_annual":   {"type": "number", "description": "Contract Services annual"},
            "expense_miscellaneous_annual":       {"type": "number", "description": "Miscellaneous annual"},
            "expense_utilities_annual":           {"type": "number", "description": "Utilities & Trash annual"},
            "expense_telephone_annual":           {"type": "number", "description": "Telephone & Communications annual"},
            "expense_marketing_annual":           {"type": "number", "description": "Marketing & Promotion annual"},
            "expense_repairs_maintenance_annual": {"type": "number", "description": "Repairs, Maintenance & Reserves annual"},
            "expense_insurance_annual":           {"type": "number", "description": "Property Insurance annual"},
            "expense_payroll_annual":             {"type": "number", "description": "Salaries, Taxes & Benefits annual"},
            "expense_property_tax_annual":        {"type": "number", "description": "Property Taxes annual"},
            "expense_mgmt_fee_annual":            {"type": "number", "description": "Third Party Management annual"},
            "expense_total_annual":               {"type": "number", "description": "Total Operating Expenses annual"},
            "noi_year_one_stated":                {"type": "number", "description": "NOI from Year 1 column"},
            "noi_current_stated":                 {"type": "number", "description": "NOI from Current column"},
        }
        for f in cls._OM_CITED_SCALAR_FIELDS + cls._OM_CITED_COLLECTION_FIELDS:
            base.update(cls._citation_props(f))
        return {"type": "object", "properties": base}

    @classmethod
    def _build_t12_schema(cls) -> dict:
        base = {
            "gpr_annual_actual":               {"type": "number"},
            "vacancy_credit_loss_pct_actual":  {"type": "number", "description": "decimal"},
            "expense_ratio_actual":            {"type": "number", "description": "decimal"},
            "other_income_annual":             {"type": "number"},
            "bad_debt_annual":                 {"type": "number"},
            "corrections_collections_annual":  {"type": "number"},
            "property_tax_annual":             {"type": "number"},
            "insurance_annual":                {"type": "number"},
            "mgmt_fee_pct_actual":             {"type": "number", "description": "decimal"},
            "payroll_annual":                  {"type": "number"},
            "repairs_maintenance_annual":      {"type": "number"},
            "utilities_annual":                {"type": "number"},
            "marketing_annual":                {"type": "number"},
            "other_opex_annual":               {"type": "number"},
            "noi_actual":                      {"type": "number"},
            "period_months":                   {"type": "integer", "description": "12 or 6"},
        }
        for f in cls._T12_SCALAR_FIELDS:
            base.update(cls._citation_props(f))
        return {"type": "object", "properties": base}

    @classmethod
    def _build_rent_roll_schema(cls) -> dict:
        base = {
            "num_units_actual":       {"type": "integer"},
            "physical_occupancy_pct": {"type": "number", "description": "decimal"},
            "avg_in_place_rent_per_unit_monthly": {"type": "number"},
            "avg_market_rent_per_unit_monthly": {"type": "number"},
            "rent_growth_pct":        {"type": "number", "description": "decimal"},
            "unit_mix": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "section":           {"type": "string"},
                        "unit_type":         {"type": "string"},
                        "size":              {"type": "string"},
                        "standard_sqft":     {"type": "number"},
                        "num_units":         {"type": "integer"},
                        "occupied_units":    {"type": "integer"},
                        "occupancy_pct":     {"type": "number", "description": "decimal"},
                        "current_rent":      {"type": "number"},
                        "market_rent":       {"type": "number"},
                        "rent_per_sqft":     {"type": "number"},
                        "potential_rent":    {"type": "number"},
                        "occupied_sqft":     {"type": "number"},
                        "total_sqft":        {"type": "number"},
                        "pct_of_total_sqft": {"type": "number", "description": "decimal"},
                    },
                },
            },
            "lease_records": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "unit_id":           {"type": "string"},
                        "monthly_rent":      {"type": "number"},
                        "lease_expiration":  {"type": "string", "description": "YYYY-MM-DD"},
                        "sqft":              {"type": "number"},
                    },
                },
            },
        }
        for f in cls._RENT_ROLL_SCALAR_FIELDS + cls._RENT_ROLL_CITED_COLLECTION_FIELDS:
            base.update(cls._citation_props(f))
        return {"type": "object", "properties": base}

    _TOOL_SCHEMAS: dict = {}  # populated after class definition

    @classmethod
    def _scalar_fields_for(cls, doc_type: str) -> list[str]:
        return {
            "om": cls._OM_SCALAR_FIELDS,
            "t12": cls._T12_SCALAR_FIELDS,
            "rent_roll": cls._RENT_ROLL_SCALAR_FIELDS,
        }[doc_type]

    @classmethod
    def _cited_collection_fields_for(cls, doc_type: str) -> list[str]:
        return {
            "om": cls._OM_CITED_COLLECTION_FIELDS,
            "t12": [],
            "rent_roll": cls._RENT_ROLL_CITED_COLLECTION_FIELDS,
        }[doc_type]

    def _extract(self, system_prompt: str, user_prompt: str, doc_type: str, schema_cls, source_context: str | None = None) -> dict:
        """Call Anthropic with tool-use structured output.

        Returns {"scalars": {field: value, ...}, "field_citations": {field: {confidence, citations, source_text}}}
        """
        tool_name = f"extract_{doc_type}"
        t0 = time.time()
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=0.0,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
                tools=[{
                    "name": tool_name,
                    "description": f"Extract structured underwriting data from this {doc_type.upper()} document.",
                    "input_schema": self._TOOL_SCHEMAS[doc_type],
                }],
                tool_choice={"type": "tool", "name": tool_name},
            )
            tool_block = next((b for b in message.content if b.type == "tool_use"), None)
            if tool_block is None:
                logger.error(f"No tool_use block in response for {doc_type}")
                return {"scalars": {}, "field_citations": {}}

            raw = tool_block.input
            scalar_keys = set(self._scalar_fields_for(doc_type))

            cleaned_scalars = {
                k: v for k, v in raw.items()
                if k in scalar_keys and v != "null" and v is not None
            }
            if doc_type == "om" and raw.get("unit_mix"):
                cleaned_scalars["unit_mix"] = raw["unit_mix"]
            if doc_type == "om" and raw.get("rent_comps"):
                repaired = repair_om_rent_comp_rows(raw["rent_comps"], source_context)
                # Deduplicate on (facility, size) — keep first occurrence
                seen = set()
                deduped = []
                for row in repaired:
                    key = (
                        (row.get("facility") or "").strip().lower(),
                        (row.get("size") or "").strip().lower(),
                    )
                    if key not in seen:
                        seen.add(key)
                        deduped.append(row)
                cleaned_scalars["rent_comps"] = deduped
            if doc_type == "rent_roll" and raw.get("unit_mix"):
                cleaned_scalars["unit_mix"] = raw["unit_mix"]
            # rent_roll: also grab lease_records (non-scalar, no companion fields)
            if doc_type == "rent_roll" and raw.get("lease_records"):
                cleaned_scalars["lease_records"] = raw["lease_records"]

            result = schema_cls(**cleaned_scalars).model_dump()

            # Build per-field citation data for every non-null scalar field
            field_citations = {}
            for field in self._OM_CITED_SCALAR_FIELDS + self._cited_collection_fields_for(doc_type):
                if result.get(field) is not None:
                    field_citations[field] = {
                        "confidence":  raw.get(f"{field}_confidence") or 0.0,
                        "citations":   raw.get(f"{field}_citations") or [],
                        "source_text": raw.get(f"{field}_source"),
                    }

            usage = message.usage
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            non_null = sum(v is not None for v in result.values())
            logger.info(
                f"Structured extraction for {doc_type}: {non_null} non-null fields, "
                f"{len(field_citations)} with citations, "
                f"tokens in={input_tokens} out={output_tokens} cache_read={cache_read} "
                f"duration={int((time.time() - t0) * 1000)}ms"
            )
            self._record_llm_metrics(input_tokens, output_tokens, cache_read, cache_write, stage=f"extract_{doc_type}")
            return {"scalars": result, "field_citations": field_citations}
        except Exception as e:
            logger.error(f"Extraction failed for {doc_type}: {e}")
            return {"scalars": {}, "field_citations": {}}

    def merge_extractions(
        self,
        om_data: dict | None,
        rent_roll_data: dict | None,
        t12_data: dict | None,
    ) -> tuple[dict, dict]:
        """Merge extractions with priority rules."""
        if not om_data:
            om_data = {}
        if not rent_roll_data:
            rent_roll_data = {}
        if not t12_data:
            t12_data = {}

        merged = {}
        citations = {}

        # Property details: OM is primary source
        for field in ["name", "asset_type", "address", "num_units", "rentable_sqft", "year_built"]:
            val = om_data.get(field)
            if val is not None:
                merged[field] = val
                citations[field] = {"doc_type": "om", "value": val}

        # Rent Roll overrides OM for occupancy, GPR, unit count
        if rent_roll_data.get("summary"):
            summary = rent_roll_data["summary"]
            if summary.get("occupancy_pct") is not None:
                merged["occupancy_pct"] = summary["occupancy_pct"]
                citations["occupancy_pct"] = {"doc_type": "rent_roll", "value": summary["occupancy_pct"]}
            if summary.get("total_units") is not None:
                merged["num_units"] = summary["total_units"]
            if summary.get("annual_gross_potential_rent"):
                merged["gross_potential_rent_annual"] = summary["annual_gross_potential_rent"]

        # Acquisition: from OM
        for field in ["purchase_price", "closing_cost_pct", "capex_reserve_per_unit"]:
            if field in om_data:
                merged[field] = om_data[field]

        # Operational income
        if om_data.get("other_income_annual"):
            merged["other_income_annual"] = om_data["other_income_annual"]
        if om_data.get("rent_growth_pct"):
            merged["rent_growth_pct"] = om_data["rent_growth_pct"]

        # Expenses: T12 overrides OM (actuals beat projections)
        # OM field names use the expense_ prefix from the new extraction schema
        OM_EXPENSE_FIELD_MAP = {
            "property_tax_annual":        "expense_property_tax_annual",
            "insurance_annual":           "expense_insurance_annual",
            "payroll_annual":             "expense_payroll_annual",
            "repairs_maintenance_annual": "expense_repairs_maintenance_annual",
            "utilities_annual":           "expense_utilities_annual",
            "marketing_annual":           "expense_marketing_annual",
        }
        for operational_field, om_field in OM_EXPENSE_FIELD_MAP.items():
            t12_val = t12_data.get("expenses", {}).get(operational_field)
            om_val = om_data.get(om_field)
            if t12_val is not None:
                merged[operational_field] = t12_val
                citations[operational_field] = {"doc_type": "t12", "value": t12_val}
            elif om_val is not None:
                merged[operational_field] = om_val
                citations[operational_field] = {"doc_type": "om", "value": om_val}

        # mgmt_fee_pct and opex_growth_pct don't have the expense_ prefix
        for field in ["mgmt_fee_pct", "opex_growth_pct"]:
            t12_val = t12_data.get("expenses", {}).get(field)
            om_val = om_data.get(field)
            if t12_val is not None:
                merged[field] = t12_val
                citations[field] = {"doc_type": "t12", "value": t12_val}
            elif om_val is not None:
                merged[field] = om_val
                citations[field] = {"doc_type": "om", "value": om_val}

        # other_opex_annual: sum the smaller OM line items that have no dedicated wizard field
        other_opex_components = [
            om_data.get("expense_office_admin_annual"),
            om_data.get("expense_bank_fees_annual"),
            om_data.get("expense_contract_services_annual"),
            om_data.get("expense_miscellaneous_annual"),
            om_data.get("expense_telephone_annual"),
        ]
        om_other_opex = sum(v for v in other_opex_components if v is not None)
        t12_other_opex = t12_data.get("expenses", {}).get("other_opex_annual")

        if t12_other_opex is not None:
            merged["other_opex_annual"] = t12_other_opex
            citations["other_opex_annual"] = {"doc_type": "t12", "value": t12_other_opex}
        elif om_other_opex > 0:
            merged["other_opex_annual"] = om_other_opex
            citations["other_opex_annual"] = {"doc_type": "om", "value": om_other_opex}

        # Financing: OM
        for field in ["loan_amount", "interest_rate", "loan_term_years", "amortization_years", "loan_type"]:
            if field in om_data:
                merged[field] = om_data[field]

        # Exit: OM
        for field in ["hold_period_years", "exit_cap_rate", "selling_cost_pct"]:
            if field in om_data:
                merged[field] = om_data[field]

        # Lease records from rent roll
        if rent_roll_data.get("leases"):
            merged["lease_records"] = rent_roll_data["leases"]

        return merged, citations

    def condense_batch(self, chunk_context: str) -> CondensedBatchExtraction:
        """Phase 1 (map): extract all financially relevant data from a chunk batch."""
        t0 = time.time()
        try:
            message = self.client.messages.parse(
                model=self.model,
                max_tokens=4096,
                temperature=0,
                system=[{
                    "type": "text",
                    "text": PHASE1_CONDENSATION_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": create_phase1_user_prompt(chunk_context)}],
                output_format=CondensedBatchExtraction,
            )
            result = message.parsed_output

            usage = message.usage
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            logger.debug(
                f"condense_batch: {len(result.fields)} fields, "
                f"tokens in={input_tokens} out={output_tokens} duration={int((time.time() - t0) * 1000)}ms"
            )
            self._record_llm_metrics(input_tokens, output_tokens, cache_read, cache_write, stage="condense_batch")
            return result
        except Exception as e:
            logger.error(f"Phase 1 condensation failed: {e}")
            return CondensedBatchExtraction()

    def reduce_to_schema(self, doc_type: str, condensed_fields: list[dict], source_context: str | None = None) -> dict:
        """Phase 2 (reduce): fit condensed fields into the typed per-doc schema."""
        condensed_json = _json.dumps(condensed_fields, indent=2)
        if doc_type == "om":
            prompt = create_phase2_om_prompt(condensed_json)
            schema_cls = OMExtraction
        elif doc_type == "t12":
            prompt = create_phase2_t12_prompt(condensed_json)
            schema_cls = T12Extraction
        else:
            prompt = create_phase2_rent_roll_prompt(condensed_json)
            schema_cls = RentRollExtraction
        tool_name = f"reduce_{doc_type}"
        t0 = time.time()
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=0,
                system=[],
                messages=[{"role": "user", "content": prompt}],
                tools=[{
                    "name": tool_name,
                    "description": f"Output the final {doc_type.upper()} schema values.",
                    "input_schema": self._TOOL_SCHEMAS[doc_type],
                }],
                tool_choice={"type": "tool", "name": tool_name},
            )
            tool_block = next((b for b in message.content if b.type == "tool_use"), None)
            if tool_block is None:
                logger.error(f"No tool_use block in reduce_to_schema for {doc_type}")
                return {"scalars": {}, "field_citations": {}}

            raw = tool_block.input
            scalar_keys = set(self._scalar_fields_for(doc_type))
            cleaned_scalars = {
                k: v for k, v in raw.items()
                if k in scalar_keys and v != "null" and v is not None
            }
            if doc_type == "om" and raw.get("unit_mix"):
                cleaned_scalars["unit_mix"] = raw["unit_mix"]
            if doc_type == "om" and raw.get("rent_comps"):
                cleaned_scalars["rent_comps"] = repair_om_rent_comp_rows(raw["rent_comps"], source_context)
            if doc_type == "rent_roll" and raw.get("unit_mix"):
                cleaned_scalars["unit_mix"] = raw["unit_mix"]
            if doc_type == "rent_roll" and raw.get("lease_records"):
                cleaned_scalars["lease_records"] = raw["lease_records"]

            result = schema_cls(**cleaned_scalars).model_dump()

            field_citations = {}
            for field in self._scalar_fields_for(doc_type):
                if result.get(field) is not None:
                    field_citations[field] = {
                        "confidence":  raw.get(f"{field}_confidence") or 0.0,
                        "citations":   raw.get(f"{field}_citations") or [],
                        "source_text": raw.get(f"{field}_source"),
                    }

            usage = message.usage
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            logger.debug(
                f"reduce_to_schema({doc_type}): {len(field_citations)} cited fields, "
                f"tokens in={input_tokens} out={output_tokens} "
                f"duration={int((time.time() - t0) * 1000)}ms"
            )
            self._record_llm_metrics(input_tokens, output_tokens, cache_read, cache_write, stage=f"reduce_to_schema_{doc_type}")
            return {"scalars": result, "field_citations": field_citations}
        except Exception as e:
            logger.error(f"Phase 2 reduce failed for {doc_type}: {e}")
            return {"scalars": {}, "field_citations": {}}


# Populate _TOOL_SCHEMAS after class definition so classmethods are available
REExtractionLLMService._TOOL_SCHEMAS = {
    "om":        REExtractionLLMService._build_om_schema(),
    "t12":       REExtractionLLMService._build_t12_schema(),
    "rent_roll": REExtractionLLMService._build_rent_roll_schema(),
}
