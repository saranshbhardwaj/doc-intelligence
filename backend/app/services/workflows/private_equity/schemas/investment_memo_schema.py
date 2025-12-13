from typing import List, Optional, Annotated
from pydantic import BaseModel, Field

# ============================================================================
# Nested Models (Bottom-Up)
# ============================================================================

class Highlight(BaseModel):
    type: str
    label: str
    value: str
    formatted: str = ""
    trend: str
    trend_value: str = ""
    detail: str = ""
    year: int = 0
    citation: str

class KeyMetric(BaseModel):
    label: str
    value: str
    period: str = ""
    status: str
    year: str = ""
    citation: str

class HistoricalFinancial(BaseModel):
    year: Annotated[int, Field(ge=1900, le=2100)]  # ✅ Correct Pydantic v2 syntax
    revenue: float = 0.0
    ebitda: float = 0.0
    margin: Annotated[float, Field(ge=0, le=1)] = -1.0
    citation: List[str] = Field(default_factory=list)

class FinancialMetrics(BaseModel):
    rev_cagr: float = 0.0
    ebitda_margin_latest: float = 0.0
    citation: List[str] = Field(default_factory=list)

class Financials(BaseModel):
    """Embedded in financial_performance section only"""
    currency: str = Field(description="Must match top-level currency")
    fiscal_year_end: str = ""
    historical: Annotated[List[HistoricalFinancial], Field(min_length=1)]
    metrics: FinancialMetrics = FinancialMetrics()

class Section(BaseModel):
    key: str
    title: str
    content: Annotated[str, Field(min_length=50, max_length=2000)]
    citations: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    highlights: List[Highlight] = Field(default_factory=list)
    key_metrics: List[KeyMetric] = Field(default_factory=list)
    financials: Financials

# ============================================================================
# Top-Level Models
# ============================================================================

class CompanyOverview(BaseModel):
    company_name: str = ""
    industry: str = ""
    headquarters: str = ""
    founded: str = ""
    description: str = ""
    citations: List[str] = Field(default_factory=list)

class KeyPerson(BaseModel):
    name: str
    title: str
    background: str = ""
    tenure_years: Annotated[int, Field(ge=0)] = 0

class Management(BaseModel):
    summary: str
    key_people: Annotated[List[KeyPerson], Field(max_length=5)] = []
    strengths: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)

class ValuationCase(BaseModel):
    ev: float
    multiple: float
    irr: float = 0.0
    assumptions: str = ""
    citations: List[str] = Field(default_factory=list)

class Valuation(BaseModel):
    base_case: ValuationCase = ValuationCase(ev=0.0, multiple=0.0)
    upside_case: ValuationCase = ValuationCase(ev=0.0, multiple=0.0)
    downside_case: ValuationCase = ValuationCase(ev=0.0, multiple=0.0)

class ESGFactor(BaseModel):
    dimension: str
    status: str
    citation: str = ""

class ESG(BaseModel):
    factors: list[ESGFactor] = Field(default_factory=list)
    overall: str = ""

class RiskItem(BaseModel):
    description: str
    category: str
    severity: str
    citations: List[str] = Field(default_factory=list)

class OpportunityItem(BaseModel):
    description: str
    category: str
    impact: str
    citations: List[str] = Field(default_factory=list)

class NextStep(BaseModel):
    priority: Annotated[int, Field(ge=1)]
    action: str
    owner: str
    timeline_days: Annotated[int, Field(ge=0)] = 0

class Meta(BaseModel):
    version: Annotated[int, Field(ge=2, le=2)]

# ============================================================================
# Root Model
# ============================================================================

class OptionalSections(BaseModel):
    company_overview: CompanyOverview = CompanyOverview()
    management: Management = Management(summary="")
    valuation: Valuation = Valuation()
    esg: ESG = ESG()
    next_steps: List[NextStep] = []
    
class InvestmentMemoOutput(BaseModel):
    """Investment Memo structured output - Version 2"""
    
    currency: str = Field(
        description="Three-letter ISO currency code for all financial figures"
    )
    sections: List[Section]
    risks: List[RiskItem] = Field(default_factory=list)
    opportunities: List[OpportunityItem] = Field(default_factory=list)
    references: List[str] = Field(
        description="All unique citations"
    )
    meta: Meta
    optional_sections: Optional[OptionalSections] = None
    inconsistencies: List[str] = Field(default_factory=list)
    
    # Optional top-level objects
    # company_overview: Optional[CompanyOverview] = None
    # management: Optional[Management] = None
    # valuation: Optional[Valuation] = None
    # esg: Optional[ESG] = None
    # next_steps: Optional[Annotated[List[NextStep], Field(min_length=1)]] = None
    # inconsistencies: List[str] = Field(default_factory=list)