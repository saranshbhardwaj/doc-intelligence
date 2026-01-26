"""Schema loader for YAML-defined Excel templates."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from app.utils.logging import logger


class TemplateSchema:
    """Represents a loaded Excel template schema."""

    def __init__(self, schema_data: Dict[str, Any]):
        self.schema_id = schema_data["schema_id"]
        self.version = schema_data["version"]
        self.name = schema_data["name"]
        self.description = schema_data.get("description", "")
        self.fingerprint = schema_data.get("fingerprint", [])
        self.fields = schema_data.get("fields", [])
        self.tables = schema_data.get("tables", [])

        # Build alias index for O(1) lookups
        self._alias_index = self._build_alias_index()

    def _build_alias_index(self) -> Dict[str, str]:
        """
        Build an index mapping lowercase aliases to field IDs.

        Returns:
            Dict mapping alias → field_id
        """
        alias_index = {}
        for field in self.fields:
            field_id = field["id"]
            for alias in field.get("pdf_aliases", []):
                alias_lower = alias.lower().strip()
                # Store all aliases pointing to this field
                # If collision, last field wins (shouldn't happen with good schema design)
                alias_index[alias_lower] = field_id

        logger.debug(f"Built alias index with {len(alias_index)} entries for {len(self.fields)} fields")
        return alias_index

    def find_field_by_alias(self, pdf_field_name: str) -> Optional[Dict[str, Any]]:
        """
        Find a schema field matching the PDF field name.

        Args:
            pdf_field_name: Name from PDF extraction

        Returns:
            Field definition dict, or None if no match
        """
        normalized = pdf_field_name.lower().strip()

        # Direct match (O(1))
        if normalized in self._alias_index:
            field_id = self._alias_index[normalized]
            return self.get_field(field_id)

        # Partial match - check if any alias is contained in PDF field name
        # (e.g., "Purchase Price (Per Unit)" matches "Purchase Price")
        for alias, field_id in self._alias_index.items():
            if alias in normalized or normalized in alias:
                logger.debug(f"Partial match: '{pdf_field_name}' → alias '{alias}' → field '{field_id}'")
                return self.get_field(field_id)

        return None

    def get_field(self, field_id: str) -> Optional[Dict[str, Any]]:
        """Get field definition by ID."""
        for field in self.fields:
            if field["id"] == field_id:
                return field
        return None

    def get_fingerprint_cells(self) -> List[Dict[str, str]]:
        """Get fingerprint cells for template identification."""
        return self.fingerprint


class SchemaLoader:
    """Loads and manages Excel template schemas from YAML files."""

    def __init__(self, schemas_dir: Optional[str] = None):
        """
        Initialize schema loader.

        Args:
            schemas_dir: Path to schemas directory. If None, uses default location.
        """
        if schemas_dir is None:
            # Default to schemas/ subdirectory
            current_dir = Path(__file__).parent
            self.schemas_dir = current_dir / "schemas"
        else:
            self.schemas_dir = Path(schemas_dir)

        if not self.schemas_dir.exists():
            logger.warning(f"Schemas directory not found: {self.schemas_dir}")

        self._schemas_cache: Dict[str, TemplateSchema] = {}

    def load_schema(self, schema_id: str) -> Optional[TemplateSchema]:
        """
        Load a schema by ID.

        Args:
            schema_id: Schema identifier (e.g., "re_investment_v1")

        Returns:
            TemplateSchema object, or None if not found
        """
        # Check cache first
        if schema_id in self._schemas_cache:
            logger.debug(f"Schema '{schema_id}' loaded from cache")
            return self._schemas_cache[schema_id]

        # Load from file
        schema_path = self.schemas_dir / f"{schema_id}.yaml"
        if not schema_path.exists():
            logger.warning(f"Schema file not found: {schema_path}")
            return None

        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_data = yaml.safe_load(f)

            # Validate required fields
            required_keys = ["schema_id", "version", "name"]
            for key in required_keys:
                if key not in schema_data:
                    raise ValueError(f"Schema missing required field: {key}")

            # Create schema object
            schema = TemplateSchema(schema_data)

            # Cache it
            self._schemas_cache[schema_id] = schema

            logger.info(
                f"Loaded schema '{schema_id}' v{schema.version}: "
                f"{len(schema.fields)} fields, {len(schema.tables)} tables"
            )

            return schema

        except Exception as e:
            logger.error(f"Failed to load schema '{schema_id}': {e}", exc_info=True)
            return None

    def list_available_schemas(self) -> List[str]:
        """
        List all available schema IDs.

        Returns:
            List of schema IDs
        """
        if not self.schemas_dir.exists():
            return []

        schema_ids = []
        for file_path in self.schemas_dir.glob("*.yaml"):
            schema_id = file_path.stem
            schema_ids.append(schema_id)

        return schema_ids

    def reload_schema(self, schema_id: str) -> Optional[TemplateSchema]:
        """
        Force reload a schema from disk (bypassing cache).

        Args:
            schema_id: Schema identifier

        Returns:
            TemplateSchema object, or None if not found
        """
        # Clear from cache
        self._schemas_cache.pop(schema_id, None)

        # Load fresh
        return self.load_schema(schema_id)
