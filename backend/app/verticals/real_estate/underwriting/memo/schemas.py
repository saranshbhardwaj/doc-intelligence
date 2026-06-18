"""Pydantic schemas for IC memo narrator output and assembled context."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    """A source-document citation. Validated post-hoc against the retrieved chunk set."""
    model_config = ConfigDict(populate_by_name=True)

    doc_id: str = Field(description="ID of the source document this citation refers to.")
    page: int = Field(ge=1, description="1-indexed page number.")


class ProseSection(BaseModel):
    """Output schema shared by 7 narrated sections: Executive Summary, Transaction Overview,
    Property Description, Market Overview, Sponsor, Financial Analysis, Rent Position."""
    model_config = ConfigDict(populate_by_name=True)

    paragraphs: list[str] = Field(
        min_length=1,
        max_length=4,
        description="2-4 short paragraphs of prose. Each is rendered as a separate Word paragraph.",
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="All [doc_id:page] references that appear inline in paragraphs.",
    )


class Risk(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(description="One sentence stating the risk.")
    severity: Literal["high", "medium", "low"]
    source: Literal[
        "verdict_warning",
        "stress_test",
        "rollover",
        "rent_position",
        "overlevered",
        "analyst_note",
    ] = Field(description="The category of supporting evidence from STRUCTURED DATA.")
    mitigant: Optional[str] = Field(
        default=None,
        description="One sentence, or null when no supportable mitigant exists.",
    )
    citation: Optional[Citation] = None


class RisksSection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    risks: list[Risk] = Field(min_length=3, max_length=6)


class Recommendation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    classification: Literal["Pursue", "Needs Review", "Below Screen"]
    rationale: str = Field(max_length=600)
    driving_metrics: list[str] = Field(
        max_length=3,
        description='Max 3 entries in the form "METRIC value vs. CRITERION value".',
    )
    conditions: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Conditions for proceeding. Empty when classification == 'Below Screen'.",
    )


# Section keys (also used as dict keys in narrator output)
SECTION_EXECUTIVE_SUMMARY = "executive_summary"
SECTION_INVESTMENT_THESIS = "investment_thesis"
SECTION_TRANSACTION_OVERVIEW = "transaction_overview"
SECTION_PROPERTY_DESCRIPTION = "property_description"
SECTION_MARKET_OVERVIEW = "market_overview"
SECTION_SPONSOR = "sponsor"
SECTION_FINANCIAL_ANALYSIS = "financial_analysis"
SECTION_RENT_POSITION = "rent_position"
SECTION_RISKS = "risks"
SECTION_RECOMMENDATION = "recommendation"

PROSE_SECTIONS = (
    SECTION_EXECUTIVE_SUMMARY,
    SECTION_INVESTMENT_THESIS,
    SECTION_TRANSACTION_OVERVIEW,
    SECTION_PROPERTY_DESCRIPTION,
    SECTION_MARKET_OVERVIEW,
    SECTION_SPONSOR,
    SECTION_FINANCIAL_ANALYSIS,
    SECTION_RENT_POSITION,
)


@dataclass
class RetrievedChunk:
    doc_id: str
    page: int
    text: str


@dataclass
class MemoContext:
    """Assembled context passed to the narrator and the docx renderer.

    Built once per memo by `data_assembler.build_memo_context()` from a fully completed
    underwriting run plus the analyst-entered cover/sponsor/notes data.
    """

    # Identity
    deal_name: str
    address: Optional[str]
    asset_type: str

    # Physical
    year_built: Optional[int]
    num_units: Optional[int]
    rentable_sqft: Optional[float]
    cc_unit_count: int
    nc_unit_count: int
    climate_control_pct: float

    # Acquisition
    purchase_price: Optional[float]
    price_per_unit: Optional[float]
    price_per_sqft: Optional[float]
    cap_rate_at_cost: Optional[float]

    # Market (pre-extracted in inputs.project)
    population_3mi: Optional[int]
    avg_household_income_3mi: Optional[float]
    storage_sqft_per_capita_3mi: Optional[float]
    nearby_storage_1mi: Optional[int]
    nearby_storage_3mi: Optional[int]
    nearby_storage_5mi: Optional[int]

    # Structured tables (raw dicts pulled from result_artifact / inputs)
    noi_buildup: dict = field(default_factory=dict)
    return_metrics: dict = field(default_factory=dict)
    noi_bridge: dict = field(default_factory=dict)
    rent_position: dict = field(default_factory=dict)
    sensitivity: dict = field(default_factory=dict)
    stress_tests: list = field(default_factory=list)
    rollover: dict = field(default_factory=dict)

    # Full annual projections (Y1..Yn) — superset of noi_buildup which is Y1 only
    projections: list = field(default_factory=list)

    # Capital stack at acquisition (purchase_price, down_payment, loan_amount,
    # closing_cost, capex_reserve_initial, total_equity_invested)
    capital_structure: dict = field(default_factory=dict)

    # Per-size-bucket rent position vs comp set (RentPositionRow list)
    rent_position_analysis: list = field(default_factory=list)

    # Sizing
    max_loan: dict = field(default_factory=dict)
    financing: dict = field(default_factory=dict)

    # Inputs reused in narration
    unit_mix: list[dict] = field(default_factory=list)
    rent_comps: list[dict] = field(default_factory=list)
    criteria: dict = field(default_factory=dict)
    capex_reserve_per_unit: Optional[float] = None

    # Verdict
    classification: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    rationale: Optional[str] = None

    # Form-entered
    cover_data: dict = field(default_factory=dict)
    sponsor_data: dict = field(default_factory=dict)
    market_notes: Optional[str] = None

    # Analyst thesis & strategy inputs (from "Thesis & Strategy" modal tab)
    thesis_text: Optional[str] = None
    strategy_type: Optional[str] = None        # Stable Income | Value-Add | Distressed | Conversion | Portfolio Build | Opportunistic
    hold_period_years_override: Optional[int] = None
    verdict_override: Optional[str] = None      # Pursue | Pass | Needs Review | None
    verdict_override_reason: Optional[str] = None
    custom_conditions: list[str] = field(default_factory=list)
    sourcing_type: Optional[str] = None
    sourcing_detail: Optional[str] = None

    # Original calculator verdict (for audit trail when override is applied)
    classification_calculator: Optional[str] = None

    # RAG hits (filled by narrator before each section is invoked)
    retrieved_chunks: dict[str, list[RetrievedChunk]] = field(default_factory=dict)

    # Source document ID list (for citation post-validation)
    document_ids: list[str] = field(default_factory=list)
