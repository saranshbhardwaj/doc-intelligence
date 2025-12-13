"""Real Estate workflow templates registry - PLACEHOLDER."""
from .property_valuation import TEMPLATE as PROPERTY_VALUATION_TEMPLATE
from .lease_analysis import TEMPLATE as LEASE_ANALYSIS_TEMPLATE
from .due_diligence import TEMPLATE as DUE_DILIGENCE_TEMPLATE

TEMPLATES = [
    PROPERTY_VALUATION_TEMPLATE,
    LEASE_ANALYSIS_TEMPLATE,
    DUE_DILIGENCE_TEMPLATE,
]

__all__ = ['TEMPLATES']
