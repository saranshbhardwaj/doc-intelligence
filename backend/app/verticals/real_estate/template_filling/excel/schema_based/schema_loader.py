"""Schema loader for YAML-defined Excel templates."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from app.utils.logging import logger
from app.verticals.real_estate.template_filling.source_map import (
    FILL_WHEN_VALUES,
    SOURCE_BASIS_VALUES,
    SOURCE_PERIOD_VALUES,
    as_list,
)


def _normalize_field_name(name: str) -> str:
    """
    Normalize a field name for fuzzy alias matching.

    Azure DI often returns labels with trailing colons, dollar signs, or
    extra whitespace (e.g., "Gross Potential Rent:" instead of "Gross Potential Rent").
    Normalizing both sides before comparison significantly increases match rate.
    """
    n = name.lower().strip()
    # Strip trailing punctuation common in Azure DI labels (colon, period, comma, semicolon)
    n = n.rstrip(':.,;!')
    # Remove currency symbols and parentheses (e.g., "Price ($)" → "Price  ")
    n = re.sub(r'[$()]', '', n)
    # Collapse multiple whitespace to single space
    n = re.sub(r'\s+', ' ', n).strip()
    return n


CONTRACT_METADATA_KEYS = ("source_period", "source_basis", "fill_when", "requires_structure")


def _can_use_static_contract_default(target: Dict[str, Any]) -> bool:
    """Only truly static, unruled fields get the legacy always/property default."""
    sheet = str(target.get("sheet") or "")
    return (
        not target.get("extraction_rule")
        and not target.get("columns")
        and sheet not in {"Actuals&UnitMix", "P&L", "Napkin"}
    )


def _apply_contract_defaults_or_raise(target: Dict[str, Any], target_type: str) -> None:
    target_id = target.get("id") or "<unknown>"
    missing = [key for key in CONTRACT_METADATA_KEYS if key not in target]
    if not missing:
        return

    has_any_contract_key = any(key in target for key in CONTRACT_METADATA_KEYS)
    if not has_any_contract_key and _can_use_static_contract_default(target):
        target["source_period"] = "static"
        target["source_basis"] = "om_property_summary"
        target["fill_when"] = ["always"]
        target["requires_structure"] = []
        return

    raise ValueError(
        f"{target_type} '{target_id}' missing contract metadata: {', '.join(missing)}"
    )


def _validate_contract_metadata(targets: List[Dict[str, Any]], target_type: str) -> None:
    for target in targets or []:
        _apply_contract_defaults_or_raise(target, target_type)
        target_id = target.get("id") or "<unknown>"

        source_period = target.get("source_period")
        if source_period not in SOURCE_PERIOD_VALUES:
            raise ValueError(
                f"{target_type} '{target_id}' has invalid source_period '{source_period}'"
            )

        source_basis = target.get("source_basis")
        if source_basis not in SOURCE_BASIS_VALUES:
            raise ValueError(
                f"{target_type} '{target_id}' has invalid source_basis '{source_basis}'"
            )

        fill_when_values = as_list(target.get("fill_when"))
        if not fill_when_values:
            raise ValueError(f"{target_type} '{target_id}' must define fill_when")
        invalid_fill_when = [value for value in fill_when_values if value not in FILL_WHEN_VALUES]
        if invalid_fill_when:
            raise ValueError(
                f"{target_type} '{target_id}' has invalid fill_when {invalid_fill_when}"
            )
        target["fill_when"] = fill_when_values

        target["requires_structure"] = as_list(target.get("requires_structure"))


class TemplateSchema:
    """Represents a loaded Excel template schema."""

    def __init__(self, schema_data: Dict[str, Any]):
        self.schema_id = schema_data["schema_id"]
        self.version = schema_data["version"]
        self.name = schema_data["name"]
        self.description = schema_data.get("description", "")
        self.total_sheets = schema_data.get("total_sheets", 0)
        self.fingerprint = schema_data.get("fingerprint", [])
        self.fields = schema_data.get("fields", [])
        self.tables = schema_data.get("tables", [])

        # Build alias index for O(1) lookups
        self._alias_index = self._build_alias_index()

    def _build_alias_index(self) -> Dict[str, str]:
        """
        Build an index mapping lowercase aliases to field IDs.

        Stores both the raw lowercase alias AND its normalized form so that
        Azure DI labels like "Gross Potential Rent:" also match the alias
        "Gross Potential Rent" (trailing colon stripped by normalization).

        Returns:
            Dict mapping alias → field_id
        """
        alias_index = {}
        for field in self.fields:
            field_id = field["id"]
            for alias in field.get("pdf_aliases", []):
                alias_lower = alias.lower().strip()
                # Raw lowercase match (original behavior)
                alias_index[alias_lower] = field_id
                # Normalized match (handles trailing punctuation / special chars)
                alias_normalized = _normalize_field_name(alias)
                if alias_normalized != alias_lower:
                    alias_index[alias_normalized] = field_id

        logger.debug(f"Built alias index with {len(alias_index)} entries for {len(self.fields)} fields")
        return alias_index

    def find_field_by_alias(self, pdf_field_name: str) -> Optional[Dict[str, Any]]:
        """
        Find a schema field matching the PDF field name.

        Matching order (highest to lowest priority):
        1. Exact lowercase match
        2. Normalized match (strips trailing colon/punctuation, collapses whitespace)
        3. Partial substring match using normalized form

        Args:
            pdf_field_name: Name from PDF extraction

        Returns:
            Field definition dict, or None if no match
        """
        normalized_raw = pdf_field_name.lower().strip()

        # 1. Direct match (O(1))
        if normalized_raw in self._alias_index:
            field_id = self._alias_index[normalized_raw]
            return self.get_field(field_id)

        # 2. Normalized match: strips trailing punctuation, removes $(), collapses spaces
        #    Handles Azure DI labels like "Gross Potential Rent:" → matches alias "Gross Potential Rent"
        normalized_clean = _normalize_field_name(pdf_field_name)
        if normalized_clean != normalized_raw and normalized_clean in self._alias_index:
            field_id = self._alias_index[normalized_clean]
            logger.debug(
                f"Normalized match: '{pdf_field_name}' → '{normalized_clean}' → field '{field_id}'"
            )
            return self.get_field(field_id)

        # 3. Partial match - check if any alias is contained in PDF field name or vice versa
        #    (e.g., "Purchase Price (Per Unit)" matches alias "Purchase Price")
        for alias, field_id in self._alias_index.items():
            if alias in normalized_clean or normalized_clean in alias:
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

            _validate_contract_metadata(schema_data.get("fields", []), "field")
            _validate_contract_metadata(schema_data.get("tables", []), "table")

            # Create schema object
            schema = TemplateSchema(schema_data)

            # Cache it
            self._schemas_cache[schema_id] = schema

            logger.info(
                f"Loaded schema '{schema_id}' v{schema.version}: "
                f"{len(schema.fields)} fields, {len(schema.tables)} tables"
            )

            return schema

        except ValueError:
            logger.error(f"Invalid schema '{schema_id}'", exc_info=True)
            raise
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
