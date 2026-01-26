"""Schema-based Excel template mapping system.

Provides deterministic field mapping for known template types using YAML schemas.
Falls back to generic analyzer for unknown templates.
"""

from .schema_loader import SchemaLoader
from .schema_mapper import SchemaMapper
from .template_identifier import TemplateIdentifier

__all__ = ["SchemaLoader", "SchemaMapper", "TemplateIdentifier"]
