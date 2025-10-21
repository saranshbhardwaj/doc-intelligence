# backend/app/models.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any  # Added Any here
from datetime import datetime

class ExtractionMetadata(BaseModel):
    """Metadata about the extraction process"""
    request_id: str
    filename: str
    pages: int
    characters_extracted: int
    processing_time_seconds: float
    timestamp: datetime = Field(default_factory=datetime.now)

class RateLimitInfo(BaseModel):
    """Rate limit information"""
    remaining_uploads: int
    reset_in_hours: int
    limit_per_window: int

class CompanyInfo(BaseModel):
    """Company information structure"""
    company_name: Optional[str] = None
    company_id: Optional[str] = None
    industry: Optional[str] = None
    secondary_industry: Optional[str] = None
    founded_year: Optional[int] = None
    employees: Optional[int] = None
    headquarters: Optional[str] = None
    business_structure: Optional[str] = None
    naics_codes: Optional[str] = None
    sic_codes: Optional[str] = None

class Financials(BaseModel):
    """Financial data structure"""
    currency: str = "USD"
    fiscal_year_end: Optional[str] = None
    revenue_by_year: Dict[str, float] = {}
    ebitda_by_year: Dict[str, float] = {}
    adjusted_ebitda_by_year: Dict[str, float] = {}
    net_income_by_year: Dict[str, float] = {}
    gross_margin_by_year: Dict[str, float] = {}
    other_metrics: Dict[str, Any] = {}  # Changed 'any' to 'Any'

class BalanceSheet(BaseModel):
    """Balance sheet data"""
    most_recent_year: Optional[int] = None
    total_assets: Optional[float] = None
    current_assets: Optional[float] = None
    fixed_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    current_liabilities: Optional[float] = None
    long_term_debt: Optional[float] = None
    stockholders_equity: Optional[float] = None
    working_capital: Optional[float] = None

class FinancialRatios(BaseModel):
    """Financial ratios"""
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    return_on_assets: Optional[float] = None
    return_on_equity: Optional[float] = None
    inventory_turnover: Optional[float] = None
    accounts_receivable_turnover: Optional[float] = None

class KeyRisk(BaseModel):
    """Individual risk item"""
    risk: str
    severity: str  # High, Medium, Low
    description: str

class ManagementMember(BaseModel):
    """Management team member"""
    name: str
    title: str
    background: Optional[str] = None

class TransactionDetails(BaseModel):
    """Transaction information"""
    seller_motivation: Optional[str] = None
    post_sale_involvement: Optional[str] = None
    auction_deadline: Optional[str] = None
    assets_for_sale: Optional[str] = None

class ExtractedData(BaseModel):
    """Complete extracted data structure"""
    company_info: CompanyInfo
    financials: Financials
    balance_sheet: BalanceSheet
    financial_ratios: FinancialRatios
    customers: Dict[str, Any] = {}  # Changed 'any' to 'Any'
    market: Dict[str, Any] = {}  # Changed 'any' to 'Any'
    key_risks: List[KeyRisk] = []
    investment_thesis: Optional[str] = None
    management_team: List[ManagementMember] = []
    transaction_details: TransactionDetails = Field(default_factory=TransactionDetails)

class ExtractionResponse(BaseModel):
    """API response for extraction"""
    success: bool
    data: ExtractedData
    metadata: ExtractionMetadata
    rate_limit: RateLimitInfo
    from_cache: bool = False

class ErrorResponse(BaseModel):
    """API error response"""
    error: str
    message: str
    request_id: Optional[str] = None

class FeedbackRequest(BaseModel):
    """User feedback on extraction"""
    request_id: str
    rating: int = Field(ge=1, le=5, description="1-5 star rating")
    comment: Optional[str] = Field(None, max_length=1000)
    email: Optional[str] = Field(None, max_length=255)
    accuracy_rating: Optional[int] = Field(None, ge=1, le=5, description="How accurate was the extraction?")
    would_pay: Optional[bool] = None
    timestamp: datetime = Field(default_factory=datetime.now)

class FeedbackResponse(BaseModel):
    """Response after submitting feedback"""
    success: bool
    message: str
    feedback_id: str

class AnalyticsEvent(BaseModel):
    """Track usage analytics"""
    event_type: str  # "page_view", "upload_start", "upload_success", "upload_error", ""
    request_id: Optional[str] = None
    client_ip: str
    user_agent: Optional[str] = None
    page_path: Optional[str] = None
    referrer: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = {}