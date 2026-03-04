"""Validation utilities for schema-based template filling.

Provides:
- Confidence thresholds for auto-fill decisions
- Data type validation for extracted values
- Fill result tracking with confidence breakdown
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field

from app.utils.logging import logger


# Confidence thresholds for fill decisions
CONFIDENCE_THRESHOLDS = {
    "auto_fill": 0.85,       # Fill automatically, high trust
    "needs_review": 0.70,    # Fill but flag for user review
    "skip": 0.50,            # Don't fill, show as unmapped
}


@dataclass
class ValidationResult:
    """Result of validating a single field value."""
    is_valid: bool
    original_value: Any
    converted_value: Any = None
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class FillConfidenceReport:
    """Report of fill operation with confidence breakdown."""
    total_mappings: int = 0
    cells_filled: int = 0
    high_confidence: int = 0      # >= 0.85
    needs_review: int = 0         # 0.70-0.84
    low_confidence: int = 0       # 0.50-0.69
    skipped: int = 0              # < 0.50
    validation_errors: int = 0

    # Details for UI
    needs_review_cells: List[Dict[str, Any]] = field(default_factory=list)
    skipped_cells: List[Dict[str, Any]] = field(default_factory=list)
    validation_error_cells: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_mappings": self.total_mappings,
            "cells_filled": self.cells_filled,
            "high_confidence": self.high_confidence,
            "needs_review": self.needs_review,
            "low_confidence": self.low_confidence,
            "skipped": self.skipped,
            "validation_errors": self.validation_errors,
            "needs_review_cells": self.needs_review_cells,
            "skipped_cells": self.skipped_cells,
            "validation_error_cells": self.validation_error_cells,
        }


class FieldValidator:
    """Validates extracted field values against expected data types."""

    @staticmethod
    def validate(value: Any, data_type: str) -> ValidationResult:
        """
        Validate a value against its expected data type.

        Args:
            value: The extracted value to validate
            data_type: Expected type (text, number, currency, percentage, date)

        Returns:
            ValidationResult with validity status and converted value
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            return ValidationResult(
                is_valid=True,
                original_value=value,
                converted_value=None,
                warnings=["Empty value"]
            )

        validators = {
            "text": FieldValidator._validate_text,
            "number": FieldValidator._validate_number,
            "currency": FieldValidator._validate_currency,
            "percentage": FieldValidator._validate_percentage,
            "date": FieldValidator._validate_date,
        }

        validator = validators.get(data_type, FieldValidator._validate_text)
        return validator(value)

    @staticmethod
    def _validate_text(value: Any) -> ValidationResult:
        """Validate text values - always valid."""
        return ValidationResult(
            is_valid=True,
            original_value=value,
            converted_value=str(value) if value is not None else None
        )

    @staticmethod
    def _validate_number(value: Any) -> ValidationResult:
        """Validate numeric values."""
        if isinstance(value, (int, float)):
            return ValidationResult(
                is_valid=True,
                original_value=value,
                converted_value=float(value)
            )

        # Try to parse string
        try:
            cleaned = str(value).replace(",", "").replace(" ", "").strip()
            num_value = float(cleaned)
            return ValidationResult(
                is_valid=True,
                original_value=value,
                converted_value=num_value
            )
        except ValueError:
            return ValidationResult(
                is_valid=False,
                original_value=value,
                error_message=f"Cannot convert '{value}' to number"
            )

    @staticmethod
    def _validate_currency(value: Any) -> ValidationResult:
        """Validate currency values."""
        if isinstance(value, (int, float)):
            return ValidationResult(
                is_valid=True,
                original_value=value,
                converted_value=float(value)
            )

        # Try to parse string with currency symbols
        try:
            cleaned = str(value).replace(",", "").replace("$", "").replace(" ", "").strip()
            # Handle parentheses for negative (e.g., ($1,000))
            if cleaned.startswith("(") and cleaned.endswith(")"):
                cleaned = "-" + cleaned[1:-1]

            num_value = float(cleaned)

            warnings = []
            if num_value < 0:
                warnings.append("Negative currency value")

            return ValidationResult(
                is_valid=True,
                original_value=value,
                converted_value=num_value,
                warnings=warnings
            )
        except ValueError:
            return ValidationResult(
                is_valid=False,
                original_value=value,
                error_message=f"Cannot convert '{value}' to currency"
            )

    @staticmethod
    def _validate_percentage(value: Any) -> ValidationResult:
        """Validate percentage values."""
        warnings = []

        if isinstance(value, (int, float)):
            num_value = float(value)
        else:
            try:
                cleaned = str(value).replace(",", "").replace("%", "").replace(" ", "").strip()
                num_value = float(cleaned)
            except ValueError:
                return ValidationResult(
                    is_valid=False,
                    original_value=value,
                    error_message=f"Cannot convert '{value}' to percentage"
                )

        # Convert to Excel decimal format if needed
        # Values > 1 are assumed to be percentages (e.g., 30 means 30%)
        converted_value = num_value
        if num_value > 1:
            converted_value = num_value / 100
            warnings.append(f"Converted {num_value}% to {converted_value}")

        # Validate reasonable range
        if converted_value < -1 or converted_value > 10:
            warnings.append(f"Percentage {converted_value * 100}% outside typical range (-100% to 1000%)")

        return ValidationResult(
            is_valid=True,
            original_value=value,
            converted_value=converted_value,
            warnings=warnings
        )

    @staticmethod
    def _validate_date(value: Any) -> ValidationResult:
        """Validate date values."""
        if isinstance(value, datetime):
            return ValidationResult(
                is_valid=True,
                original_value=value,
                converted_value=value
            )

        # Try common date formats
        date_formats = [
            "%m/%d/%Y", "%m/%d/%y",
            "%Y-%m-%d",
            "%d/%m/%Y", "%d/%m/%y",
            "%B %d, %Y", "%b %d, %Y",
            "%Y",  # Just year
        ]

        str_value = str(value).strip()

        for fmt in date_formats:
            try:
                parsed = datetime.strptime(str_value, fmt)
                return ValidationResult(
                    is_valid=True,
                    original_value=value,
                    converted_value=parsed
                )
            except ValueError:
                continue

        # If we can't parse it, return as string (Excel might handle it)
        return ValidationResult(
            is_valid=True,
            original_value=value,
            converted_value=str_value,
            warnings=["Could not parse as date, passing as string"]
        )


def categorize_confidence(confidence: float) -> str:
    """
    Categorize a confidence score into action category.

    Args:
        confidence: Confidence score (0.0 to 1.0)

    Returns:
        Category: "auto_fill", "needs_review", "low_confidence", or "skip"
    """
    if confidence >= CONFIDENCE_THRESHOLDS["auto_fill"]:
        return "auto_fill"
    elif confidence >= CONFIDENCE_THRESHOLDS["needs_review"]:
        return "needs_review"
    elif confidence >= CONFIDENCE_THRESHOLDS["skip"]:
        return "low_confidence"
    else:
        return "skip"


def should_fill_cell(confidence: float, min_threshold: Optional[float] = None) -> bool:
    """
    Determine if a cell should be filled based on confidence.

    Args:
        confidence: Confidence score (0.0 to 1.0)
        min_threshold: Override minimum threshold (default: CONFIDENCE_THRESHOLDS["skip"])

    Returns:
        True if cell should be filled
    """
    threshold = min_threshold if min_threshold is not None else CONFIDENCE_THRESHOLDS["skip"]
    return confidence >= threshold


def create_confidence_report(
    mappings: List[Dict[str, Any]],
    pdf_fields: List[Dict[str, Any]],
    validation_errors: Optional[List[Dict[str, Any]]] = None
) -> FillConfidenceReport:
    """
    Create a confidence report for a set of mappings.

    Args:
        mappings: List of field mappings with confidence scores
        pdf_fields: List of PDF fields with extracted_value
        validation_errors: Optional list of validation errors

    Returns:
        FillConfidenceReport with breakdown
    """
    report = FillConfidenceReport(total_mappings=len(mappings))

    # Build lookup for PDF fields
    pdf_field_lookup = {f.get("id"): f for f in pdf_fields}

    for mapping in mappings:
        confidence = mapping.get("confidence", 0.0)
        category = categorize_confidence(confidence)

        pdf_field_id = mapping.get("pdf_field_id")
        pdf_field = pdf_field_lookup.get(pdf_field_id, {})
        has_value = bool(pdf_field.get("extracted_value"))

        cell_info = {
            "excel_sheet": mapping.get("excel_sheet"),
            "excel_cell": mapping.get("excel_cell"),
            "excel_label": mapping.get("excel_label"),
            "pdf_field_name": mapping.get("pdf_field_name"),
            "confidence": confidence,
            "has_value": has_value,
            "source": mapping.get("source", "unknown"),
        }

        if category == "auto_fill":
            report.high_confidence += 1
            if has_value:
                report.cells_filled += 1
        elif category == "needs_review":
            report.needs_review += 1
            report.needs_review_cells.append(cell_info)
            if has_value:
                report.cells_filled += 1
        elif category == "low_confidence":
            report.low_confidence += 1
            report.needs_review_cells.append(cell_info)
            if has_value:
                report.cells_filled += 1
        else:  # skip
            report.skipped += 1
            report.skipped_cells.append(cell_info)

    # Add validation errors
    if validation_errors:
        report.validation_errors = len(validation_errors)
        report.validation_error_cells = validation_errors

    return report
