# app/services/risk_detector.py
"""
Automated red flag detection based on quantitative rules.
Supplements LLM-extracted risks with systematic pattern detection.
"""
from typing import List, Dict, Optional, Any
from app.models import ExtractedData
from app.utils.logging import logger


class RedFlag:
    """Represents a detected red flag"""
    def __init__(
        self,
        flag: str,
        severity: str,
        category: str,
        description: str,
        metrics: Dict[str, Any],
        rule_triggered: str
    ):
        self.flag = flag
        self.severity = severity  # "High", "Medium", "Low"
        self.category = category  # "Financial", "Operational", "Market", "Transaction"
        self.description = description
        self.metrics = metrics  # Supporting data
        self.rule_triggered = rule_triggered  # Which rule detected this


class RiskDetector:
    """Detect financial and operational red flags from extracted data"""

    # Thresholds
    MARGIN_DECLINE_THRESHOLD = 0.03  # 3 percentage points
    HIGH_DEBT_TO_EQUITY = 3.0
    HIGH_DEBT_TO_EBITDA = 5.0
    LOW_CURRENT_RATIO = 1.5
    HIGH_CUSTOMER_CONCENTRATION = 0.50  # 50%
    HIGH_CAPEX_PCT = 0.15  # 15% of revenue
    NEGATIVE_CAGR_THRESHOLD = -0.05  # -5%

    def __init__(self):
        self.red_flags: List[RedFlag] = []

    def detect_all(self, data: ExtractedData) -> List[Dict[str, Any]]:
        """
        Run all detection rules and return list of red flags.
        Returns list of dicts for easy serialization.
        """
        self.red_flags = []

        # Financial red flags
        self._check_declining_margins(data)
        self._check_high_leverage(data)
        self._check_negative_cash_flow(data)
        self._check_declining_revenue(data)
        self._check_liquidity(data)
        self._check_profitability(data)

        # Operational red flags
        self._check_customer_concentration(data)
        self._check_high_capex(data)

        # Convert to dicts for JSON serialization
        return [self._to_dict(flag) for flag in self.red_flags]

    def _add_flag(
        self,
        flag: str,
        severity: str,
        category: str,
        description: str,
        metrics: Dict[str, Any],
        rule: str
    ):
        """Helper to add a red flag"""
        self.red_flags.append(RedFlag(flag, severity, category, description, metrics, rule))

    def _check_declining_margins(self, data: ExtractedData):
        """Detect declining gross margins"""
        if not data.financials or not data.financials.gross_margin_by_year:
            return

        margins = data.financials.gross_margin_by_year
        if len(margins) < 2:
            return

        # Get sorted years (exclude projected)
        historical_years = sorted([y for y in margins.keys() if not y.startswith("projected")])
        if len(historical_years) < 2:
            return

        # Compare most recent two years
        latest = historical_years[-1]
        previous = historical_years[-2]

        latest_margin = margins[latest]
        previous_margin = margins[previous]

        if latest_margin is not None and previous_margin is not None:
            decline = previous_margin - latest_margin

            if decline >= self.MARGIN_DECLINE_THRESHOLD:
                self._add_flag(
                    flag="Declining Gross Margin",
                    severity="High",
                    category="Financial",
                    description=f"Gross margin declined {decline*100:.1f} percentage points "
                                f"from {previous_margin*100:.1f}% ({previous}) to {latest_margin*100:.1f}% ({latest}). "
                                f"Indicates pricing pressure, rising costs, or unfavorable product mix.",
                    metrics={
                        "previous_year": previous,
                        "previous_margin": previous_margin,
                        "latest_year": latest,
                        "latest_margin": latest_margin,
                        "decline_pp": round(decline * 100, 1)
                    },
                    rule="gross_margin_decline_3pp"
                )

    def _check_high_leverage(self, data: ExtractedData):
        """Detect high debt levels"""
        # Check Debt/Equity ratio
        if data.financial_ratios and data.financial_ratios.debt_to_equity is not None:
            d_e = data.financial_ratios.debt_to_equity

            if d_e > self.HIGH_DEBT_TO_EQUITY:
                severity = "High" if d_e > 5.0 else "Medium"
                self._add_flag(
                    flag="High Debt-to-Equity Ratio",
                    severity=severity,
                    category="Financial",
                    description=f"Debt-to-equity ratio of {d_e:.2f}x exceeds healthy threshold "
                                f"({self.HIGH_DEBT_TO_EQUITY:.1f}x). Indicates high financial leverage "
                                f"and potential solvency risk.",
                    metrics={"debt_to_equity": d_e, "threshold": self.HIGH_DEBT_TO_EQUITY},
                    rule="debt_to_equity_high"
                )

        # Check Debt/EBITDA ratio
        if data.financial_ratios and data.financial_ratios.net_debt_to_ebitda is not None:
            d_ebitda = data.financial_ratios.net_debt_to_ebitda

            if d_ebitda > self.HIGH_DEBT_TO_EBITDA:
                severity = "High" if d_ebitda > 7.0 else "Medium"
                self._add_flag(
                    flag="High Debt-to-EBITDA Ratio",
                    severity=severity,
                    category="Financial",
                    description=f"Net debt-to-EBITDA ratio of {d_ebitda:.2f}x exceeds typical PE comfort level "
                                f"({self.HIGH_DEBT_TO_EBITDA:.1f}x). May limit flexibility for add-on acquisitions.",
                    metrics={"net_debt_to_ebitda": d_ebitda, "threshold": self.HIGH_DEBT_TO_EBITDA},
                    rule="debt_to_ebitda_high"
                )

    def _check_negative_cash_flow(self, data: ExtractedData):
        """Detect chronic negative free cash flow"""
        if not data.operating_metrics or not data.operating_metrics.fcf_by_year:
            return

        fcf = data.operating_metrics.fcf_by_year
        if len(fcf) < 2:
            return

        # Get sorted historical years
        historical_years = sorted([y for y in fcf.keys() if not y.startswith("projected")])
        if len(historical_years) < 2:
            return

        # Count consecutive negative FCF years
        negative_years = [year for year in historical_years if fcf.get(year, 0) < 0]

        if len(negative_years) >= 2:
            severity = "High" if len(negative_years) >= 3 else "Medium"
            latest_fcf = fcf.get(historical_years[-1], 0)

            self._add_flag(
                flag="Chronic Negative Free Cash Flow",
                severity=severity,
                category="Financial",
                description=f"Negative free cash flow in {len(negative_years)} of last {len(historical_years)} years. "
                            f"Latest FCF: {latest_fcf:,.0f}. Indicates business consumes cash and may require "
                            f"additional capital injections.",
                metrics={
                    "negative_years": negative_years,
                    "total_years": len(historical_years),
                    "latest_fcf": latest_fcf
                },
                rule="negative_fcf_consecutive"
            )

    def _check_declining_revenue(self, data: ExtractedData):
        """Detect declining revenue trends"""
        if not data.growth_analysis or data.growth_analysis.historical_cagr is None:
            return

        cagr = data.growth_analysis.historical_cagr

        if cagr < self.NEGATIVE_CAGR_THRESHOLD:
            self._add_flag(
                flag="Declining Revenue",
                severity="High",
                category="Financial",
                description=f"Historical revenue CAGR of {cagr*100:.1f}% indicates declining business. "
                            f"May signal market share loss, industry headwinds, or product obsolescence.",
                metrics={"historical_cagr": cagr, "threshold": self.NEGATIVE_CAGR_THRESHOLD},
                rule="negative_revenue_cagr"
            )

    def _check_liquidity(self, data: ExtractedData):
        """Detect liquidity concerns"""
        if not data.financial_ratios or data.financial_ratios.current_ratio is None:
            return

        current_ratio = data.financial_ratios.current_ratio

        if current_ratio < self.LOW_CURRENT_RATIO:
            severity = "High" if current_ratio < 1.0 else "Medium"
            self._add_flag(
                flag="Low Liquidity (Current Ratio)",
                severity=severity,
                category="Financial",
                description=f"Current ratio of {current_ratio:.2f} is below healthy level "
                            f"({self.LOW_CURRENT_RATIO:.1f}). May struggle to meet short-term obligations.",
                metrics={"current_ratio": current_ratio, "threshold": self.LOW_CURRENT_RATIO},
                rule="low_current_ratio"
            )

    def _check_profitability(self, data: ExtractedData):
        """Detect profitability issues"""
        if not data.financial_ratios or data.financial_ratios.ebitda_margin is None:
            return

        ebitda_margin = data.financial_ratios.ebitda_margin

        if ebitda_margin < 0:
            self._add_flag(
                flag="Negative EBITDA Margin",
                severity="High",
                category="Financial",
                description=f"EBITDA margin of {ebitda_margin*100:.1f}% indicates unprofitable operations. "
                            f"Business is not generating cash from core operations.",
                metrics={"ebitda_margin": ebitda_margin},
                rule="negative_ebitda_margin"
            )
        elif ebitda_margin < 0.10:  # Less than 10%
            self._add_flag(
                flag="Low EBITDA Margin",
                severity="Medium",
                category="Financial",
                description=f"EBITDA margin of {ebitda_margin*100:.1f}% is below typical PE target (10%+). "
                            f"Limited operating leverage and margin for error.",
                metrics={"ebitda_margin": ebitda_margin, "threshold": 0.10},
                rule="low_ebitda_margin"
            )

    def _check_customer_concentration(self, data: ExtractedData):
        """Detect customer concentration risk"""
        if not data.customers or data.customers.top_customer_concentration_pct is None:
            return

        concentration = data.customers.top_customer_concentration_pct

        if concentration > self.HIGH_CUSTOMER_CONCENTRATION:
            severity = "High" if concentration > 0.70 else "Medium"
            self._add_flag(
                flag="High Customer Concentration",
                severity=severity,
                category="Operational",
                description=f"Top customers represent {concentration*100:.0f}% of revenue. "
                            f"Loss of a major customer could severely impact business viability.",
                metrics={
                    "concentration_pct": concentration,
                    "threshold": self.HIGH_CUSTOMER_CONCENTRATION,
                    "description": data.customers.top_customer_concentration
                },
                rule="customer_concentration_high"
            )

    def _check_high_capex(self, data: ExtractedData):
        """Detect high capital intensity"""
        if not data.financial_ratios or data.financial_ratios.capex_pct_revenue is None:
            return

        capex_pct = data.financial_ratios.capex_pct_revenue

        if capex_pct > self.HIGH_CAPEX_PCT:
            self._add_flag(
                flag="High Capital Intensity",
                severity="Medium",
                category="Operational",
                description=f"CapEx represents {capex_pct*100:.1f}% of revenue, indicating capital-intensive business. "
                            f"May limit cash available for debt service and distributions.",
                metrics={"capex_pct_revenue": capex_pct, "threshold": self.HIGH_CAPEX_PCT},
                rule="high_capex_intensity"
            )

    def _to_dict(self, flag: RedFlag) -> Dict[str, Any]:
        """Convert RedFlag to dict for JSON serialization"""
        return {
            "flag": flag.flag,
            "severity": flag.severity,
            "category": flag.category,
            "description": flag.description,
            "metrics": flag.metrics,
            "rule_triggered": flag.rule_triggered,
            "source": "automated_detection"
        }


# Global instance
risk_detector = RiskDetector()


def detect_red_flags(data: ExtractedData) -> List[Dict[str, Any]]:
    """
    Convenience function to detect red flags.
    Returns list of red flag dicts.
    """
    try:
        flags = risk_detector.detect_all(data)
        logger.info(f"Detected {len(flags)} automated red flags")
        return flags
    except Exception as e:
        logger.exception(f"Error detecting red flags: {e}")
        return []
