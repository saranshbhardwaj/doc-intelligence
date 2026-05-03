"""Per-user underwriting threshold overrides.

Sparse model — every field is optional. Unset fields fall back to the canonical
defaults defined in `verdict._DEFAULTS` (industry minimums) and the existing
`InvestmentCriteria` defaults (investor targets).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UserUnderwritingThresholds(BaseModel):
    """Per-user defaults for the self-storage underwriting verdict box."""

    model_config = ConfigDict(extra="ignore")

    # Investor targets — used to prefill InvestmentCriteria on the wizard
    target_irr: Optional[float] = Field(default=None, description="Target IRR (e.g., 0.15 = 15%)")
    target_cash_on_cash: Optional[float] = Field(default=None, description="Target year-1 cash-on-cash")
    target_equity_multiple: Optional[float] = Field(default=None, description="Target equity multiple")
    max_ltv: Optional[float] = Field(default=None, description="Maximum LTV ceiling")

    # Industry-minimum overrides — gates inside verdict.evaluate()
    dscr_year_one_floor: Optional[float] = Field(default=None, description="Minimum acceptable Year 1 DSCR")
    stress_dscr_floor: Optional[float] = Field(default=None, description="Minimum DSCR under any stress scenario")
    rollover_risk_pct: Optional[float] = Field(default=None, description="Rollover-risk warning threshold (fraction of rent expiring within 12 months)")
