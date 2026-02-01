from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# ============================================================================
# ULTRA-SIMPLIFIED for Haiku 4.5 Structured Outputs
# ============================================================================

class Highlight(BaseModel):
    """Minimal highlight - just label, value, citation"""
    label: str
    value: str
    citation: str

class KeyMetric(BaseModel):
    """Simplified metric - no optional fields"""
    label: str
    value: str
    citation: str

class FinancialYear(BaseModel):
    """Minimal financial year"""
    year: int
    revenue: str
    citation: str

class Financials(BaseModel):
    """Minimal financials - no nested metrics"""
    currency: str
    historical: List[FinancialYear]

class Section(BaseModel):
    """Core section with minimal nesting"""
    key: str
    title: str
    content: str
    citations: List[str]
    highlights: List[Highlight] = Field(default_factory=list)
    confidence: Optional[float] = None
    key_metrics: List[KeyMetric] = Field(default_factory=list)
    financials: Optional[Financials] = None

class Risk(BaseModel):
    description: str
    severity: str
    citations: List[str]

class Opportunity(BaseModel):
    description: str
    impact: str
    citations: List[str]

class CompanyOverview(BaseModel):
    """Flat company overview"""
    company_name: str = ""
    industry: str = ""
    headquarters: str = ""
    description: str = ""

class ESGFactor(BaseModel):
    dimension: str
    status: str
    citation: str

class ESG(BaseModel):
    factors: List[ESGFactor] = Field(default_factory=list)
    overall: str = ""

class InvestmentMemo(BaseModel):
    """Minimal viable schema for Haiku 4.5"""
    currency: str
    sections: List[Section]
    risks: List[Risk] = Field(default_factory=list)
    opportunities: List[Opportunity] = Field(default_factory=list)
    references: List[str] = Field(default_factory=list)
    
    # ✅ FIX: Use Dict[str, Any] instead of dict, List[Any] instead of list
    company_overview: CompanyOverview = Field(default_factory=CompanyOverview)
    management: Dict[str, Any] = Field(default_factory=dict)
    valuation: Dict[str, Any] = Field(default_factory=dict)
    esg: ESG = Field(default_factory=ESG)
    next_steps: List[Dict[str, Any]] = Field(default_factory=list)
    inconsistencies: List[str] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=lambda: {"version": 2})