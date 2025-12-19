"""Vertical configuration system.

Defines features, routes, and settings for each vertical.
Can be easily extended to environment variables for microservices.
"""
from typing import Dict, List
from dataclasses import dataclass


@dataclass
class VerticalConfig:
    """Configuration for a vertical/domain."""
    name: str
    slug: str  # private_equity, real_estate
    description: str
    features: List[str]  # List of enabled features
    navigation_items: List[Dict]  # UI navigation structure
    db_prefix: str = None  # For future database separation


VERTICAL_CONFIGS: Dict[str, VerticalConfig] = {
    "private_equity": VerticalConfig(
        name="Private Equity",
        slug="private_equity",
        description="Investment analysis and deal flow platform",
        features=[
            "document_library",
            "free_form_chat",
            "workflows",
            "extraction",
            "comparison",  # Future
        ],
        navigation_items=[
            {"label": "Library", "path": "/pe/library", "icon": "book"},
            {"label": "Chat", "path": "/pe/chat", "icon": "message"},
            {"label": "Workflows", "path": "/pe/workflows", "icon": "flow"},
            {"label": "Extraction", "path": "/pe/extraction", "icon": "extract"},
            {"label": "Comparison", "path": "/pe/comparison", "icon": "compare", "coming_soon": True},
        ],
        db_prefix="pe",
    ),
    "real_estate": VerticalConfig(
        name="Real Estate",
        slug="real_estate",
        description="Real estate analysis with Excel template filling",
        features=[
            "document_library",
            "free_form_chat",
            "excel_templates",
            "template_filling",
        ],
        navigation_items=[
            {"label": "Library", "path": "/re/library", "icon": "book"},
            {"label": "Chat", "path": "/re/chat", "icon": "message"},
            {"label": "Templates", "path": "/re/templates", "icon": "template"},
            {"label": "Fills", "path": "/re/fills", "icon": "spreadsheet"},
        ],
        db_prefix="re",
    ),
}


def get_vertical_config(vertical: str) -> VerticalConfig:
    """Get configuration for a vertical."""
    if vertical not in VERTICAL_CONFIGS:
        raise ValueError(f"Unknown vertical: {vertical}")
    return VERTICAL_CONFIGS[vertical]


def get_vertical_features(vertical: str) -> List[str]:
    """Get enabled features for a vertical."""
    return get_vertical_config(vertical).features


def is_feature_enabled(vertical: str, feature: str) -> bool:
    """Check if a feature is enabled for a vertical."""
    return feature in get_vertical_features(vertical)
