# backend/app/models.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from datetime import datetime

# ---------- Helper small models ----------
class Provenance(BaseModel):
    """Where a field/value came from in the doc (optional)."""
    section_heading: Optional[str] = None
    page_numbers: Optional[List[int]] = None
    text_excerpt: Optional[str] = None

class TimeSeriesItem(BaseModel):
    """Optional array-style timeseries (alternate to dict-style)."""
    year_key: str  # e.g., "2023" or "projected_2025"
    value: Optional[float] = None
    unit: Optional[str] = None
    note: Optional[str] = None

# ---------- Core models ----------
class ExtractionMetadata(BaseModel):
    request_id: str
    filename: str
    file_label: Optional[str] = None   # human friendly label (date + name + id)
    pages: Optional[int] = None
    characters_extracted: Optional[int] = None
    processing_time_seconds: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_scanned_pdf: Optional[bool] = False
    ocr_used: Optional[bool] = False

class CompanyInfo(BaseModel):
    company_name: Optional[str] = None
    company_id: Optional[str] = None
    industry: Optional[str] = None
    secondary_industry: Optional[str] = None
    founded_year: Optional[int] = None
    employees: Optional[int] = None
    headquarters: Optional[str] = None
    website: Optional[str] = None
    business_structure: Optional[str] = None
    naics_codes: Optional[str] = None
    sic_codes: Optional[str] = None
    # optional: provenance + confidence for the whole block (coarse)
    provenance: Optional[Provenance] = None
    confidence: Optional[float] = None  # 0..1

class Financials(BaseModel):
    currency: Optional[str] = "USD"
    fiscal_year_end: Optional[str] = None
    # Keep dict style (backwards compat). Keys like "2023" or "projected_2025"
    revenue_by_year: Dict[str, float] = Field(default_factory=dict)
    ebitda_by_year: Dict[str, float] = Field(default_factory=dict)
    adjusted_ebitda_by_year: Dict[str, float] = Field(default_factory=dict)
    net_income_by_year: Dict[str, float] = Field(default_factory=dict)
    gross_margin_by_year: Dict[str, float] = Field(default_factory=dict)
    other_metrics: Dict[str, Any] = Field(default_factory=dict)
    # optional array representation (if you prefer uniform lists)
    revenue_timeseries: Optional[List[TimeSeriesItem]] = None
    ebitda_timeseries: Optional[List[TimeSeriesItem]] = None
    provenance: Optional[Provenance] = None
    confidence: Optional[float] = None

class BalanceSheet(BaseModel):
    most_recent_year: Optional[int] = None
    total_assets: Optional[float] = None
    current_assets: Optional[float] = None
    fixed_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    current_liabilities: Optional[float] = None
    long_term_debt: Optional[float] = None
    stockholders_equity: Optional[float] = None
    working_capital: Optional[float] = None
    provenance: Optional[Provenance] = None
    confidence: Optional[float] = None

class FinancialRatios(BaseModel):
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    return_on_assets: Optional[float] = None
    return_on_equity: Optional[float] = None
    inventory_turnover: Optional[float] = None
    accounts_receivable_turnover: Optional[float] = None
    # derived ratios
    ebitda_margin: Optional[float] = None
    capex_pct_revenue: Optional[float] = None
    net_debt_to_ebitda: Optional[float] = None
    provenance: Optional[Provenance] = None
    confidence: Optional[float] = None

class KeyRisk(BaseModel):
    risk: str
    severity: Optional[str] = None  # "High"/"Medium"/"Low"
    description: Optional[str] = None
    inferred: Optional[bool] = False  # inferred by model vs explicit section
    mitigation: Optional[str] = None
    provenance: Optional[Provenance] = None
    confidence: Optional[float] = None

class ManagementMember(BaseModel):
    name: str
    title: Optional[str] = None
    background: Optional[str] = None
    linkedin: Optional[str] = None
    provenance: Optional[Provenance] = None
    confidence: Optional[float] = None

class CustomerInfo(BaseModel):
    total_count: Optional[int] = None
    top_customer_concentration: Optional[str] = None
    top_customer_concentration_pct: Optional[float] = None
    customer_retention_rate: Optional[str] = None
    notable_customers: Optional[List[str]] = None
    recurring_revenue_pct: Optional[float] = None
    revenue_mix_by_segment: Optional[Dict[str, float]] = None
    provenance: Optional[Provenance] = None
    confidence: Optional[float] = None

class MarketInfo(BaseModel):
    market_size: Optional[str] = None
    market_size_estimate: Optional[float] = None
    market_growth_rate: Optional[str] = None
    competitive_position: Optional[str] = None
    market_share: Optional[str] = None
    provenance: Optional[Provenance] = None
    confidence: Optional[float] = None

class TransactionDetails(BaseModel):
    seller_motivation: Optional[str] = None
    post_sale_involvement: Optional[str] = None
    auction_deadline: Optional[str] = None
    assets_for_sale: Optional[str] = None
    deal_type: Optional[str] = None  # e.g., "majority", "minority", "divestiture"
    asking_price: Optional[float] = None
    implied_valuation_hint: Optional[str] = None
    provenance: Optional[Provenance] = None
    confidence: Optional[float] = None

class GrowthAnalysis(BaseModel):
    historical_cagr: Optional[float] = None  # as decimal, e.g., 0.15 = 15%
    projected_cagr: Optional[float] = None   # as decimal
    organic_pct: Optional[float] = None      # as decimal, e.g., 0.80 = 80%
    m_and_a_pct: Optional[float] = None      # as decimal, e.g., 0.20 = 20%
    
    # NEW: Text descriptions for context
    organic_growth_estimate: Optional[str] = None  # Text explanation
    m_and_a_summary: Optional[str] = None          # Text explanation of M&A impact
    notes: Optional[str] = None                    # Additional context
    
    provenance: Optional[Provenance] = None
    confidence: Optional[float] = None

class ValuationMultiples(BaseModel):
    """Purchase and exit multiples"""
    asking_ev_ebitda: Optional[float] = None
    asking_ev_revenue: Optional[float] = None
    asking_price_ebitda: Optional[float] = None
    exit_ev_ebitda_estimate: Optional[float] = None
    comparable_multiples_range: Optional[str] = None  # e.g., "8-12x EBITDA"
    provenance: Optional[Provenance] = None
    confidence: Optional[float] = None

class CapitalStructure(BaseModel):
    """Debt and equity structure"""
    existing_debt: Optional[float] = None
    debt_to_ebitda: Optional[float] = None
    proposed_leverage: Optional[float] = None  # e.g., 5.0x
    equity_contribution_estimate: Optional[float] = None
    provenance: Optional[Provenance] = None
    confidence: Optional[float] = None

class OperatingMetrics(BaseModel):
    """Key operating KPIs"""
    capex_by_year: Optional[Dict[str, float]] = None
    fcf_by_year: Optional[Dict[str, float]] = None  # Free Cash Flow
    working_capital_pct_revenue: Optional[float] = None
    pricing_power: Optional[str] = None  # "High", "Medium", "Low"
    contract_structure: Optional[str] = None  # Description
    provenance: Optional[Provenance] = None
    confidence: Optional[float] = None

class StrategicRationale(BaseModel):
    """Deal thesis and strategic fit"""
    deal_thesis: Optional[str] = None  # Why this deal makes sense
    value_creation_plan: Optional[str] = None  # How to improve the business
    add_on_opportunities: Optional[str] = None  # Bolt-on acquisition potential
    competitive_advantages: Optional[List[str]] = None  # USPs
    key_risks_summary: Optional[str] = None
    provenance: Optional[Provenance] = None
    confidence: Optional[float] = None

class ExtractedData(BaseModel):
    company_info: Optional[CompanyInfo] = Field(default_factory=CompanyInfo)
    financials: Optional[Financials] = Field(default_factory=Financials)
    balance_sheet: Optional[BalanceSheet] = Field(default_factory=BalanceSheet)
    financial_ratios: Optional[FinancialRatios] = Field(default_factory=FinancialRatios)
    customers: Optional[CustomerInfo] = Field(default_factory=CustomerInfo)
    market: Optional[MarketInfo] = Field(default_factory=MarketInfo)
    key_risks: List[KeyRisk] = Field(default_factory=list)
    investment_thesis: Optional[str] = None
    management_team: List[ManagementMember] = Field(default_factory=list)
    transaction_details: Optional[TransactionDetails] = Field(default_factory=TransactionDetails)

    # Derived metrics & analysis (computed by model or post-processor)
    derived_metrics: Optional[Dict[str, Any]] = None
    # growth breakdown
    growth_analysis: Optional[GrowthAnalysis] = None

    valuation_multiples: Optional[ValuationMultiples] = None
    capital_structure: Optional[CapitalStructure] = None
    operating_metrics: Optional[OperatingMetrics] = None
    strategic_rationale: Optional[StrategicRationale] = None

    # Automated red flag detection (quantitative rules applied to extracted data)
    red_flags: Optional[List[Dict[str, Any]]] = Field(default_factory=list)

    # raw sections map (heading -> text + pages) useful for UI and audit
    raw_sections: Optional[Dict[str, Dict[str, Any]]] = None
    # per-field confidence & provenance maps (non-breaking — optional)
    field_confidence: Optional[Dict[str, float]] = None
    field_provenance: Optional[Dict[str, Provenance]] = None

    # notes, free-text explanation of extraction choices
    extraction_notes: Optional[str] = None

class ExtractionResponse(BaseModel):
    success: bool
    data: ExtractedData
    metadata: ExtractionMetadata
    from_cache: bool = False

class ErrorResponse(BaseModel):
    error: str
    message: str
    request_id: Optional[str] = None

# Feedback and analytics (same as you had but kept here for convenience)
class FeedbackRequest(BaseModel):
    request_id: str
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)
    email: Optional[str] = Field(None, max_length=255)
    accuracy_rating: Optional[int] = Field(None, ge=1, le=5)
    would_pay: Optional[bool] = None
    timestamp: datetime = Field(default_factory=datetime.now)

class FeedbackResponse(BaseModel):
    success: bool
    message: str
    feedback_id: str

class AnalyticsEvent(BaseModel):
    event_type: str
    request_id: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    page_path: Optional[str] = None
    referrer: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

# ---------- Extraction List Model ----------
class ExtractionListItem(BaseModel):
    id: str
    document_id: Optional[str]
    filename: Optional[str]
    page_count: Optional[int]
    status: str
    created_at: Optional[datetime]
    completed_at: Optional[datetime]
    cost_usd: Optional[float]
    parser_used: Optional[str]
    from_cache: Optional[bool]
    error_message: Optional[str]
    
class PaginatedExtractionResponse(BaseModel):
    """Paginated response for extraction list"""
    items: list[ExtractionListItem]
    total: int
    limit: int
    offset: int


# ---------- Chat Session Models ----------
class CreateSessionRequest(BaseModel):
    """Request to create a new chat session"""
    title: Optional[str] = None
    description: Optional[str] = None
    document_ids: Optional[List[str]] = None  # Optional list of document IDs to add


class UpdateSessionRequest(BaseModel):
    """Request to update a chat session"""
    title: Optional[str] = None
    description: Optional[str] = None


class AddDocumentsRequest(BaseModel):
    """Request to add documents to a session"""
    document_ids: List[str] = Field(..., min_items=1)  # At least one document required


class SessionDocumentInfo(BaseModel):
    """Document information in a session"""
    id: str
    name: str
    added_at: datetime


class SessionResponse(BaseModel):
    """Response containing session data"""
    id: str
    title: Optional[str]
    description: Optional[str]
    message_count: int
    document_count: int = 0  # Count of documents in session
    created_at: datetime
    updated_at: datetime
    documents: List[SessionDocumentInfo] = Field(default_factory=list)