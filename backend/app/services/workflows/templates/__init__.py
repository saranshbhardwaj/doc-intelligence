"""Workflow templates registry.

Import individual template modules and expose a list for seeding / version management.
"""
from .investment_memo import TEMPLATE as INVESTMENT_MEMO_TEMPLATE
from .red_flags import TEMPLATE as RED_FLAGS_TEMPLATE
from .revenue_quality import TEMPLATE as REVENUE_QUALITY_TEMPLATE
from .financial_model import TEMPLATE as FINANCIAL_MODEL_TEMPLATE
from .management_assessment import TEMPLATE as MANAGEMENT_ASSESSMENT_TEMPLATE

TEMPLATES = [
    INVESTMENT_MEMO_TEMPLATE,
    RED_FLAGS_TEMPLATE,
    REVENUE_QUALITY_TEMPLATE,
    FINANCIAL_MODEL_TEMPLATE,
    MANAGEMENT_ASSESSMENT_TEMPLATE,
]
