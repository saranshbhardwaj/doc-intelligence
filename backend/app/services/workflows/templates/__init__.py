"""DEPRECATED: Legacy templates registry.

This module is kept for backward compatibility.
New code should use app.services.workflows.core.registry instead.
"""
# Import from new locations for backward compatibility
from app.services.workflows.private_equity.templates import TEMPLATES

__all__ = ['TEMPLATES']
