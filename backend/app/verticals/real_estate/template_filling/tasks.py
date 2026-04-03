"""Celery tasks for Excel template filling pipeline.

Task Flow:
1. analyze_template_task: Analyze uploaded Excel to detect fillable cells
2. detect_fields_task: Analyze PDF to identify structured fields (LLM call 1)
3. auto_map_fields_task: Match PDF fields to Excel cells (LLM call 2)
4. extract_data_task: Extract values from PDF (LLM call 3)
5. fill_excel_task: Fill Excel template with data (openpyxl)
6. start_fill_run_chain: Orchestrate the full pipeline
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from celery import chain, shared_task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.repositories.document_repository import DocumentRepository
from app.repositories.job_repository import JobRepository
from app.repositories.template_repository import TemplateRepository
from app.services.artifacts import persist_artifact
from app.services.beta_limits import commit_shadow_credits, reverse_shadow_credits
from app.services.citations import normalize_citations
from app.services.job_tracker import JobProgressTracker
from app.core.storage.storage_factory import get_storage_backend
from app.utils.costs import compute_llm_cost
from app.utils.logging import logger
from app.utils.metrics_recorder import record_template_fill_completed, record_template_fill_failed
from app.utils.metrics import TEMPLATE_FILL_LATENCY_SECONDS
from app.verticals.real_estate.template_filling.excel_handler import ExcelHandler
from app.verticals.real_estate.template_filling.llm_service import TemplateFillLLMService
from app.verticals.real_estate.template_filling.excel.mapping_coordinator import coordinator as mapping_coordinator


def _get_db_session() -> Session:
    """Get a new database session."""
    return SessionLocal()


def _reverse_template_fill_shadow(fill_run_id: str, reason: str, stage: str) -> None:
    reverse_shadow_credits(
        operation_type="template_fill_run",
        reference_id=fill_run_id,
        reason=reason,
        metadata={"stage": stage},
    )


def _extract_schema_table_row_labels(schema_obj: Any, workbook: Any) -> Dict[str, Any]:
    """
    Extract row labels for schema tables from the Excel template.

    Returns:
        Dict: {table_id: {"row_labels": [...], "start_row": int, "end_row": int}}
    """
    labels_by_table: Dict[str, Any] = {}
    if not schema_obj or not workbook:
        return labels_by_table

    for table in getattr(schema_obj, "tables", []) or []:
        table_id = table.get("id")
        sheet_name = table.get("sheet")
        row_id_col = table.get("row_identifier_column")
        start_row = table.get("data_start_row")
        end_row = table.get("data_end_row", start_row)

        if not table_id or not sheet_name or not row_id_col or not start_row:
            continue
        if sheet_name not in workbook.sheetnames:
            continue

        sheet = workbook[sheet_name]
        row_labels = []
        for row in range(start_row, (end_row or start_row) + 1):
            cell_value = sheet[f"{row_id_col}{row}"].value
            row_labels.append(str(cell_value).strip() if cell_value is not None else "")

        labels_by_table[table_id] = {
            "row_labels": row_labels,
            "start_row": start_row,
            "end_row": end_row,
        }

    return labels_by_table



def _get_table_batch_key(table_def: Dict[str, Any]) -> str:
    sheet = table_def.get("sheet") or "unknown"
    return sheet.lower()


def _compute_schema_counts(schema_obj: Any) -> Dict[str, Any]:
    fields = getattr(schema_obj, "fields", []) or []
    tables = getattr(schema_obj, "tables", []) or []
    total_table_cells = 0
    total_table_rows = 0
    total_table_columns = 0
    unknown_row_tables = 0

    for table in tables:
        columns = [c for c in (table.get("columns") or []) if c.get("excel_column")]
        col_count = len(columns)
        total_table_columns += col_count

        start_row = table.get("data_start_row")
        end_row = table.get("data_end_row")
        if start_row and end_row and end_row >= start_row:
            row_count = end_row - start_row + 1
            total_table_rows += row_count
            total_table_cells += row_count * col_count
        else:
            unknown_row_tables += 1

    return {
        "schema_id": getattr(schema_obj, "schema_id", None),
        "yaml_field_count": len(fields),
        "yaml_table_count": len(tables),
        "yaml_table_rows": total_table_rows,
        "yaml_table_columns": total_table_columns,
        "yaml_table_cells": total_table_cells,
        "yaml_tables_with_unknown_rows": unknown_row_tables,
        "total_yaml_fields": len(fields) + total_table_cells,
    }


def _build_yaml_cell_status(
    schema_obj: Any,
    mappings: List[Dict[str, Any]]
) -> Dict[str, Any]:
    target_by_key: Dict[str, Dict[str, Any]] = {}
    unknown_row_tables: List[Dict[str, Any]] = []

    for field in getattr(schema_obj, "fields", []) or []:
        sheet_name = field.get("sheet")
        value_cell = field.get("value_cell")
        if not sheet_name or not value_cell:
            continue
        key = f"{sheet_name}::{value_cell}"
        target_by_key[key] = {
            "excel_sheet": sheet_name,
            "excel_cell": value_cell,
            "target_type": "field",
            "target_id": field.get("id"),
        }

    for table in getattr(schema_obj, "tables", []) or []:
        table_id = table.get("id")
        sheet_name = table.get("sheet")
        start_row = table.get("data_start_row")
        end_row = table.get("data_end_row")
        row_identifier_col = table.get("row_identifier_column")

        if not sheet_name:
            continue

        if not start_row or not end_row or end_row < start_row:
            unknown_row_tables.append({
                "table_id": table_id,
                "sheet": sheet_name,
            })
            continue

        table_columns = [
            c.get("excel_column")
            for c in (table.get("columns") or [])
            if c.get("excel_column") and c.get("excel_column") != row_identifier_col
        ]

        for row_num in range(start_row, end_row + 1):
            for excel_col in table_columns:
                excel_cell = f"{excel_col}{row_num}"
                key = f"{sheet_name}::{excel_cell}"
                target_by_key[key] = {
                    "excel_sheet": sheet_name,
                    "excel_cell": excel_cell,
                    "target_type": "table",
                    "target_id": table_id,
                }

    mapped_keys = set()
    for mapping in mappings or []:
        sheet_name = mapping.get("excel_sheet")
        excel_cell = mapping.get("excel_cell")
        if not sheet_name or not excel_cell:
            continue
        key = f"{sheet_name}::{excel_cell}"
        if key in target_by_key:
            mapped_keys.add(key)

    all_target_cells = list(target_by_key.values())
    mapped_cells = [target_by_key[k] for k in target_by_key if k in mapped_keys]
    unmapped_cells = [target_by_key[k] for k in target_by_key if k not in mapped_keys]

    return {
        "all_target_cells": all_target_cells,
        "mapped_cells": mapped_cells,
        "unmapped_cells": unmapped_cells,
        "unknown_row_tables": unknown_row_tables,
        "total_target_cells": len(all_target_cells),
        "mapped_target_cells": len(mapped_cells),
        "unmapped_target_cells": len(unmapped_cells),
    }


@shared_task(bind=True)
def analyze_template_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze an uploaded Excel template to detect fillable cells, formulas, sheets.

    Args:
        payload: {
            "template_id": str,
            "file_path": str,  # Local path or storage key
            "job_id": str (optional)
        }

    Returns:
        Updated payload with schema_metadata
    """
    template_id = payload["template_id"]
    file_path = payload["file_path"]
    job_id = payload.get("job_id")

    db = _get_db_session()
    repo = TemplateRepository(db)
    tracker = JobProgressTracker(db, job_id) if job_id else None

    try:
        logger.info(f"Analyzing template: {template_id}")

        if tracker:
            tracker.update_progress(
                status="analyzing",
                current_stage="template_analysis",
                progress_percent=10,
                message="Analyzing Excel template structure"
            )

        # Initialize Excel handler
        handler = ExcelHandler()

        # Get template to determine file extension
        template = repo.get_template(template_id)
        file_ext = template.file_extension if template else ".xlsx"

        # Download from storage if needed
        if not Path(file_path).exists():
            storage = get_storage_backend()
            local_path = f"/tmp/{template_id}{file_ext}"
            storage.download(file_path, local_path)
            file_path = local_path

        # Analyze template
        schema_metadata = handler.analyze_template(file_path)

        # If template matches a known YAML schema, persist schema-level totals
        # so UI can report YAML target fields (not all detected Excel fillables).
        schema_summary = None
        workbook = None
        try:
            from openpyxl import load_workbook

            workbook = load_workbook(file_path, data_only=False)
            schema_id = mapping_coordinator.identify_template(workbook)
            if schema_id:
                schema_obj = mapping_coordinator.schema_loader.load_schema(schema_id)
                if schema_obj:
                    schema_summary = _compute_schema_counts(schema_obj)
        except Exception as schema_err:
            logger.warning(
                f"Could not compute YAML schema summary during template analysis: {schema_err}"
            )
        finally:
            if workbook is not None:
                try:
                    workbook.close()
                except Exception:
                    pass

        if isinstance(schema_metadata, dict) and schema_summary:
            schema_metadata["schema_summary"] = schema_summary
            schema_metadata["total_yaml_fields"] = schema_summary.get("total_yaml_fields")

        # Update template with schema
        repo.update_template(
            template_id,
            schema_metadata=schema_metadata
        )

        db.close()

        total_kv = schema_metadata.get('total_key_value_fields', 0)
        total_tables = schema_metadata.get('total_tables', 0)

        logger.info(
            f"Template analysis complete: {total_kv} key-value fields, {total_tables} tables"
        )

        if tracker:
            tracker.update_progress(
                status="completed",
                current_stage="template_analysis",
                progress_percent=100,
                message=f"Template analyzed: {total_kv} key-value fields, {total_tables} tables detected"
            )

        payload["schema_metadata"] = schema_metadata
        return {"status": "completed", **payload}

    except Exception as e:
        logger.error(f"Template analysis failed: {e}", exc_info=True)
        if tracker:
            tracker.update_progress(
                status="failed",
                current_stage="template_analysis",
                message=f"Template analysis failed: {str(e)}"
            )
        db.close()
        return {"status": "failed", "error": str(e), **payload}


@shared_task(bind=True)
def detect_fields_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Detect structured fields from PDF using Azure DI key-value pairs and tables.

    This replaces expensive LLM field detection with FREE Azure DI extraction.
    Extracts fields from:
    1. Key-value chunks (section_type="key_value_pairs")
    2. Table chunks (section_type="table")

    Args:
        payload: {
            "fill_run_id": str,
            "document_id": str,
            "job_id": str
        }

    Returns:
        Updated payload with detected fields
    """
    fill_run_id = payload["fill_run_id"]
    document_id = payload["document_id"]
    job_id = payload["job_id"]

    db = _get_db_session()
    repo = TemplateRepository(db)
    tracker = JobProgressTracker(db, job_id)

    fill_run = repo.get_fill_run(fill_run_id)
    if not fill_run:
        raise ValueError(f"Fill run not found: {fill_run_id}")
    org_id = fill_run.org_id

    # Idempotency guard: skip if already past field detection (re-queued after worker restart)
    _DETECT_DONE_STATUSES = {"fields_detected", "mapping", "awaiting_review", "filling", "completed", "failed"}
    if fill_run.status in _DETECT_DONE_STATUSES:
        logger.warning(
            f"detect_fields_task skipped — fill_run={fill_run_id} already in status={fill_run.status!r}"
        )
        db.close()
        return {**payload, "detection_result": {"fields": fill_run.field_mapping.get("pdf_fields", []) if fill_run.field_mapping else [], "total_fields": 0, "categories": []}}

    try:
        logger.info(f"Detecting fields for fill run: {fill_run_id}")

        tracker.update_progress(
            status="detecting_fields",
            current_stage="field_detection",
            progress_percent=20,
            message="Extracting fields from Azure DI key-value pairs and tables"
        )

        # Get document
        document_repo = DocumentRepository()
        document = document_repo.get_by_id(document_id, org_id)
        if not document:
            raise ValueError(f"Document not found: {document_id}")

        # Get template to count Excel schema cells (not PDF detected fields)
        template = repo.get_template(fill_run.template_id)
        schema_cell_count = 0
        if template and template.schema_metadata and template.schema_metadata.get("schema_summary"):
            # Count: KV fields + all table columns
            sch_summary = template.schema_metadata.get("schema_summary")
            fields = sch_summary.get("yaml_field_count", [])
            tables = sch_summary.get("yaml_table_cells", [])
            schema_cell_count = template.schema_metadata.get("total_yaml_fields")

        # Get KV and table chunks from document
        chunks = document_repo.get_chunks_for_document(document_id)

        if not chunks:
            raise ValueError(f"No chunks found for document {document_id}. Document may not be fully processed.")

        start_time = time.time()
        detected_fields = []
        field_id_counter = 1

        # ========================================================================
        # Extract fields from KEY-VALUE chunks
        # ========================================================================
        kv_chunks = []
        table_chunks = []
        narrative_chunks = []

        for chunk in chunks:
            # Parse metadata
            metadata = chunk.chunk_metadata or {}
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}

            # section_type is a database COLUMN, not in metadata JSON
            section_type = chunk.section_type or ""

            if section_type == "key_value_pairs":
                kv_chunks.append((chunk, metadata))
            elif section_type == "table":
                table_chunks.append((chunk, metadata))
            else:
                narrative_chunks.append((chunk, metadata))


        logger.info(f"Found {len(kv_chunks)} key-value chunks, {len(table_chunks)} table chunks, and {len(narrative_chunks)} narrative chunks")

        # Process KV chunks
        for chunk, metadata in kv_chunks:
            kv_pairs = metadata.get("key_value_pairs", [])

            for kv in kv_pairs:
                key = kv.get("key", "")
                value = kv.get("value", "")
                confidence = kv.get("confidence", 0.95)
                # Use bbox page if available (physical PDF page from Azure DI bounding_regions)
                # This is more accurate than page_number which may contain document's internal numbering
                kv_bbox = kv.get("bbox", {})
                kv_page_number = (
                    (kv_bbox.get("page") if isinstance(kv_bbox, dict) and kv_bbox else None)
                    or kv.get("page_number")
                    or metadata.get("page_number")
                    or chunk.page_number
                )
                if isinstance(kv_page_number, str) and kv_page_number.isdigit():
                    kv_page_number = int(kv_page_number)
                citation = f"[S{field_id_counter}:p{kv_page_number}]"

                if not key:
                    continue

                field_data = {
                    "id": f"kv_{field_id_counter}",
                    "name": key,
                    "type": "text",
                    "extracted_value": value or "",
                    "confidence": confidence,
                    "citations": [citation],
                    "description": f"Key-value field from page {kv_page_number}",
                    "source": "key_value_pairs"
                }
                if kv_bbox:
                    field_data["bbox"] = kv_bbox

                # DEBUG: Log first field's bbox
                if field_id_counter == 1:
                    logger.info(f"[FIELD_DETECTION] First KV field: '{key}', "
                              f"page={kv_page_number}, has bbox: {kv_bbox is not None}, bbox={kv_bbox}")

                detected_fields.append(field_data)
                field_id_counter += 1

        # ========================================================================
        # Extract fields from TABLE chunks
        # ========================================================================
        for chunk, metadata in table_chunks:
            # Extract complete table dict from chunk.tables (primary source - has ALL data from Azure DI)
            # Handle both parsed (list) and stringified (JSON string) formats from DB
            table_dict = None
            if chunk.tables:
                tables_data = chunk.tables
                # If tables_data is a JSON string, parse it first
                if isinstance(tables_data, str):
                    try:
                        tables_data = json.loads(tables_data)
                    except (json.JSONDecodeError, TypeError):
                        tables_data = None

                # Extract first table dict from parsed list
                if isinstance(tables_data, list) and len(tables_data) > 0:
                    try:
                        table_dict = tables_data[0]
                    except (IndexError, TypeError):
                        pass

            # Fallback: build minimal table dict from metadata (limited to 2 rows)
            if not table_dict:
                table_dict = {
                    "table_name": metadata.get("table_name", ""),
                    "column_headers": metadata.get("column_headers", []),
                    "table_data": metadata.get("table_data", []),
                    "page_number": metadata.get("page_number"),
                }

            # Extract table metadata from table_dict (single source of truth)
            table_name = table_dict.get("table_name", "")
            column_headers = table_dict.get("column_headers", [])
            chunk_bbox = metadata.get("bbox", {})  # Bbox is metadata-specific for PDF highlighting

            # Determine table page for citations (prefer table_dict.page_number)
            table_page = table_dict.get("page_number")
            if not table_page:
                # Fallback: derive from metadata or chunk
                page_range = metadata.get("page_range", [])
                metadata_page = metadata.get("page_number")
                range_page = page_range[0] if isinstance(page_range, list) and page_range else None
                table_page = (
                    (chunk_bbox.get("page") if isinstance(chunk_bbox, dict) and chunk_bbox else None)
                    or metadata_page
                    or range_page
                    or chunk.page_number
                )
            if isinstance(table_page, str) and table_page.isdigit():
                table_page = int(table_page)
            citation = f"[S{field_id_counter}:p{table_page}]"

            # Extract table data for per-column fields (schema matching - Stage 1)
            table_data_rows = table_dict.get("table_data", [])

            # Create per-column fields for schema alias matching (Stage 1)
            for col_header in column_headers:
                if not col_header or col_header.lower() in ["", "none", "n/a"]:
                    continue

                # Get sample value from first row
                extracted_value = ""
                if table_data_rows and len(table_data_rows) > 0:
                    try:
                        col_idx = column_headers.index(col_header)
                        if col_idx < len(table_data_rows[0]):
                            extracted_value = table_data_rows[0][col_idx]
                    except (ValueError, IndexError):
                        pass

                field_data = {
                    "id": f"tbl_{field_id_counter}",
                    "name": col_header,
                    "type": "text",
                    "extracted_value": extracted_value,
                    "confidence": 0.9,  # NOTE: Hardcoded for tables (Azure DI doesn't provide per-cell confidence)
                    "citations": [citation],
                    "description": f"Column from table '{table_name}' on page {table_page}",
                    "source": "table"
                }

                if chunk_bbox:
                    field_data["bbox"] = chunk_bbox

                # DEBUG: Log first table field's bbox
                if len([f for f in detected_fields if f.get("source") == "table"]) == 0:
                    logger.info(f"[FIELD_DETECTION] First table field: '{col_header}', "
                              f"page={table_page}, has bbox: {chunk_bbox is not None}, bbox={chunk_bbox}")

                detected_fields.append(field_data)
                field_id_counter += 1

            # Create one table_block field per table with full row data for LLM context (Stage 1.5)
            # Pass the complete table_dict from chunk.tables directly (already well-structured)
            if column_headers:
                detected_fields.append({
                    "id": f"tbl_block_{field_id_counter}",
                    "name": table_dict.get("table_name", "Table"),
                    "type": "table",
                    "extracted_value": "",
                    "confidence": 0.9,
                    "citations": [citation],
                    "source": "table_block",
                    # Pass complete table structure from chunk.tables
                    "table_name": table_dict.get("table_name", ""),
                    "table_columns": table_dict.get("column_headers", []),
                    "table_rows": table_dict.get("table_data", []),
                    "page_number": table_dict.get("page_number"),
                })
                field_id_counter += 1

        # ========================================================================
        # Extract fields from NARRATIVE chunks (for LLM context)
        # ========================================================================
        for chunk, metadata in narrative_chunks:
            narrative_text = chunk.text or ""
            if not narrative_text.strip():
                continue

            # Extract section heading from metadata
            metadata_dict = metadata if isinstance(metadata, dict) else {}
            section_heading = ""
            if isinstance(metadata_dict.get("heading_hierarchy"), list):
                section_heading = metadata_dict["heading_hierarchy"][-1] if metadata_dict["heading_hierarchy"] else ""

            # Get page number for citation
            narrative_page = metadata_dict.get("page_number") or chunk.page_number
            if isinstance(narrative_page, str) and narrative_page.isdigit():
                narrative_page = int(narrative_page)
            citation = f"[S{field_id_counter}:p{narrative_page}]"

            # Create one narrative_block field with full text for LLM context
            # Narrative provides market/economic/demographic context for better field matching
            detected_fields.append({
                "id": f"narrative_block_{field_id_counter}",
                "name": f"narrative: {section_heading}" if section_heading else "narrative",
                "type": "narrative",
                "extracted_value": narrative_text[:300],  # Summary (first 300 chars)
                "confidence": 0.8,
                "citations": [citation],
                "source": "narrative_block",
                # Full narrative text for LLM context
                "full_text": narrative_text,
                "section": section_heading,
            })
            field_id_counter += 1

        elapsed_ms = int((time.time() - start_time) * 1000)

        # DEBUG: Count fields with bbox
        fields_with_bbox = sum(1 for f in detected_fields if "bbox" in f)
        kv_fields_with_bbox = sum(1 for f in detected_fields if f.get("source") == "key_value_pairs" and "bbox" in f)
        table_fields_with_bbox = sum(1 for f in detected_fields if f.get("source") == "table" and "bbox" in f)
        logger.info(f"[FIELD_DETECTION] Summary: {len(detected_fields)} total fields, "
                  f"{fields_with_bbox} with bbox ({kv_fields_with_bbox} KV + {table_fields_with_bbox} table)")

        # Build detection result in same format as LLM would return
        detection_result = {
            "fields": detected_fields,
            "total_fields": len(detected_fields),
            "categories": ["key_value_pairs", "tables"]
        }

        # Update fill run with detected fields
        field_mapping = {
            "pdf_fields": detected_fields,
            "mappings": []  # Empty initially, will be filled by auto-mapping
        }

        # Use schema cell count as total_fields_detected (Excel cells to fill, not PDF extracted fields)
        total_to_detect = schema_cell_count if schema_cell_count > 0 else len(detected_fields)

        repo.update_fill_run(
            fill_run_id,
            field_mapping=field_mapping,
            total_fields_detected=total_to_detect,
            field_detection_completed=True,
            status="fields_detected",
            current_stage="field_detection",
        )

        db.close()

        logger.info(
            f"Field detection complete: {len(detected_fields)} fields detected "
            f"({len([f for f in detected_fields if f['source'] == 'key_value_pairs'])} from KV, "
            f"{len([f for f in detected_fields if f['source'] == 'table'])} from tables) "
            f"in {elapsed_ms}ms (Azure DI extraction - no LLM cost!)"
        )

        tracker.update_progress(
            status="fields_detected",
            current_stage="field_detection",
            progress_percent=40,
            message=f"Detected {len(detected_fields)} fields from PDF (Azure DI)"
        )

        payload["detection_result"] = detection_result
        payload["processing_time_ms"] = elapsed_ms
        return {"status": "completed", **payload}

    except SoftTimeLimitExceeded:
        logger.warning(f"detect_fields_task soft time limit exceeded for fill_run={fill_run_id}")
        repo.update_fill_run(fill_run_id, status="failed", error_stage="field_detection",
                             error_message="Task timed out (soft limit)")
        tracker.mark_error(error_stage="field_detection", error_message="Field detection timed out",
                           error_type="timeout", is_retryable=False)
        _reverse_template_fill_shadow(fill_run_id, "field_detection_timeout", "field_detection")
        db.close()
        return {"status": "failed", "error": "timeout", **payload}

    except Exception as e:
        logger.error(f"Field detection failed: {e}", exc_info=True)

        repo.update_fill_run(
            fill_run_id,
            status="failed",
            error_stage="field_detection",
            error_message=str(e)
        )

        tracker.update_progress(
            status="failed",
            current_stage="field_detection",
            message=f"Field detection failed: {str(e)}"
        )
        _reverse_template_fill_shadow(fill_run_id, "field_detection_failed", "field_detection")

        db.close()
        return {"status": "failed", "error": str(e), **payload}


@shared_task(bind=True)
def auto_map_fields_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Auto-map PDF fields to Excel cells using schema-first, then LLM fallback.

    Workflow:
    1. Try schema-based mapping (deterministic, instant)
    2. Fall back to generic + LLM for unmapped cells
    3. Merge results (schema takes priority)

    Args:
        payload: {
            "fill_run_id": str,
            "template_id": str,
            "detection_result": dict,
            "job_id": str,
            "status": str (optional, "failed" if previous task failed),
            "use_schema_only": bool (optional, default False - skip generic if True),
            "skip_schema": bool (optional, default False - skip schema if True)
        }

    Returns:
        Updated payload with mapping result
    """
    # Check if previous task failed
    if payload.get("status") == "failed":
        logger.warning(f"Skipping auto-mapping because field detection failed: {payload.get('error')}")
        return payload  # Pass through the failed status

    fill_run_id = payload["fill_run_id"]
    template_id = payload["template_id"]
    detection_result = payload["detection_result"]
    job_id = payload["job_id"]

    # Config flags (read from settings if not in payload)
    # skip_generic_mapping controls Stage 2 (generic Excel mapping) - Default: True (skip generic, run only targeted)
    skip_generic_mapping = payload.get("skip_generic_mapping", True)
    # skip_schema controls Stage 1 (schema alias matching) - Default: False (run alias matching)
    # Set to True to SKIP alias matching and send ALL YAML fields to targeted LLM extraction instead
    skip_schema = payload.get("skip_schema", True)

    db = _get_db_session()
    repo = TemplateRepository(db)
    tracker = JobProgressTracker(db, job_id)

    # Idempotency guard: skip if already past auto-mapping (re-queued after worker restart)
    _fill_run_check = repo.get_fill_run(fill_run_id)
    _AUTO_MAP_DONE_STATUSES = {"awaiting_review", "filling", "completed", "failed"}
    if _fill_run_check and _fill_run_check.status in _AUTO_MAP_DONE_STATUSES:
        logger.warning(
            f"auto_map_fields_task skipped — fill_run={fill_run_id} already in status={_fill_run_check.status!r}"
        )
        db.close()
        return {**payload, "mapping_result": _fill_run_check.field_mapping or {}}

    try:
        logger.info(f"Auto-mapping fields for fill run: {fill_run_id}")

        tracker.update_progress(
            status="mapping",
            current_stage="auto_mapping",
            progress_percent=50,
            message="Mapping PDF fields to Excel cells"
        )

        # Get template
        template = repo.get_template(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        excel_schema = template.schema_metadata
        if not excel_schema:
            raise ValueError(f"Template schema not found: {template_id}")

        # Mutable copy — Stage 2 injects virtual pdf_fields for targeted values
        pdf_fields = list(detection_result.get("fields", []))
        schema_mappings = []
        generic_mappings = []
        schema_id = None  # Track for Stage 2
        schema_obj = None
        schema_table_row_labels: Dict[str, Any] = {}
        schema_summary: Optional[Dict[str, Any]] = None

        # === STEP 1: Identify template schema (always, regardless of skip_schema) ===
        # Schema identification is separate from alias mapping creation.
        # We identify the schema for Stage 1.5 targeted LLM, but only create mappings if skip_schema=False.
        template_path = None
        workbook = None
        try:
            from openpyxl import load_workbook

            # Download template file from R2 to worker-local /tmp
            storage = get_storage_backend()
            template_path = storage.download_to_temp(template.file_path)

            # Load workbook for fingerprint check
            workbook = load_workbook(template_path, data_only=False)

            # Identify template (ALWAYS, regardless of skip_schema flag)
            schema_id = mapping_coordinator.identify_template(workbook)

            if schema_id:
                logger.info(f"✓ Template identified as: {schema_id}")
                # Extract row labels for schema tables (used in targeted table extraction)
                schema_obj_for_rows = mapping_coordinator.schema_loader.load_schema(schema_id)
                if schema_obj_for_rows:
                    schema_obj = schema_obj_for_rows
                    schema_table_row_labels = _extract_schema_table_row_labels(schema_obj_for_rows, workbook)
                    schema_summary = _compute_schema_counts(schema_obj_for_rows)
                    logger.info(
                        "YAML schema summary: fields=%s table_cells=%s total=%s",
                        schema_summary.get("yaml_field_count"),
                        schema_summary.get("yaml_table_cells"),
                        schema_summary.get("total_yaml_fields"),
                    )

                # === STEP 1a: Create schema mappings (only if skip_schema=False) ===
                if not skip_schema:
                    schema_mappings = mapping_coordinator.create_schema_mappings(schema_id, pdf_fields)

                    logger.info(f"Schema mapping: {len(schema_mappings)} fields mapped (confidence=0.98 baseline)")

                    # Log unmapped schema fields (diagnostics)
                    try:
                        from app.verticals.real_estate.template_filling.excel.schema_based import SchemaMapper

                        schema = mapping_coordinator.schema_loader.load_schema(schema_id)
                        if schema:
                            mapper = SchemaMapper(schema)
                            unmapped_field_ids = mapper.get_unmapped_schema_fields(schema_mappings)
                            if unmapped_field_ids:
                                logger.warning(
                                    f"Schema fields without PDF data ({len(unmapped_field_ids)}): "
                                    f"{', '.join(unmapped_field_ids[:10])}"
                                    f"{'...' if len(unmapped_field_ids) > 10 else ''}"
                                )
                    except Exception as e:
                        logger.debug(f"Could not check unmapped schema fields: {e}")

                    tracker.update_progress(
                        status="mapping",
                        current_stage="auto_mapping",
                        progress_percent=50,
                        message=f"Schema matched {len(schema_mappings)} fields by alias"
                    )
                else:
                    logger.info("Skipping alias mapping (skip_schema=True) — will use LLM only for schema fields")
            else:
                logger.info("Template not recognized by schema system - will use generic analyzer")

        except Exception as e:
            logger.warning(f"Schema identification failed (will fall back to generic): {e}")
            schema_mappings = []
            schema_id = None
        finally:
            # Always clean up — even if load_workbook or identify_template throws
            if workbook is not None:
                try:
                    workbook.close()
                except Exception:
                    pass
            if template_path:
                Path(template_path).unlink(missing_ok=True)

        # === STEP 1.5: Targeted LLM for unmapped YAML fields (Stage 2) ===
        # Ask LLM specifically: "find values for these 63 named fields in the Azure DI data"
        # Much cheaper and more accurate than the generic 6-batch sheet mapper for schema fields.
        # Always runs when schema is available (independent of skip_generic_mapping)
        llm_service_targeted = None
        if schema_id:
            try:
                from app.verticals.real_estate.template_filling.excel.schema_based import SchemaMapper

                schema_obj = mapping_coordinator.schema_loader.load_schema(schema_id)
                if schema_obj:
                    mapper_for_unmapped = SchemaMapper(schema_obj)
                    unmapped_field_ids = mapper_for_unmapped.get_unmapped_schema_fields(schema_mappings)
                    unmapped_fields = [
                        schema_obj.get_field(fid)
                        for fid in unmapped_field_ids
                        if schema_obj.get_field(fid) is not None
                    ]

                    schema_tables = schema_obj.tables or []

                    if unmapped_fields or schema_tables:
                        llm_service_targeted = TemplateFillLLMService(
                            prompt_version=settings.re_template_prompt_version,
                            capture_io_log=settings.capture_llm_io_log,
                            fill_run_id=fill_run_id,
                        )

                    if unmapped_fields:
                        logger.info(
                            f"🎯 Stage 2: {len(unmapped_fields)} unmapped YAML fields → targeted LLM"
                        )
                        tracker.update_progress(
                            status="mapping",
                            current_stage="auto_mapping",
                            progress_percent=55,
                            message=f"Finding values for {len(unmapped_fields)} schema fields..."
                        )

                        targeted_values = asyncio.run(
                            llm_service_targeted.extract_schema_field_values(
                                unmapped_fields, pdf_fields
                            )
                        )

                        targeted_mappings = mapping_coordinator.create_targeted_schema_mappings(
                            unmapped_fields, targeted_values
                        )

                        # Inject virtual pdf_fields so fill_excel_task can look up extracted values.
                        # TemplateFiller looks up: llm_extracted[pdf_field_id] = {value: ...}
                        # fill_excel_task populates llm_extracted from pdf_fields[*].extracted_value
                        for field_def in unmapped_fields:
                            fid = field_def["id"]
                            if fid in targeted_values:
                                result = targeted_values[fid]
                                pdf_fields.append({
                                    "id": f"targeted_{fid}",
                                    "name": fid,
                                    "type": field_def.get("data_type", "text"),
                                    "extracted_value": result["value"],
                                    "confidence": result["confidence"],
                                    "citations": normalize_citations(result.get("citations", [])),
                                    "reasoning": result.get("reasoning"),
                                    "source": "targeted_schema",
                                })

                        # Merge targeted mappings into schema_mappings so they're
                        # excluded from the Stage 3 generic pass automatically
                        schema_mappings = schema_mappings + targeted_mappings

                        # Celery heartbeat: yield to heartbeat handler between LLM calls
                        self.update_state(
                            state="PROGRESS",
                            meta={"stage": "targeted_schema_mapping_done"}
                        )

                        tracker.update_progress(
                            status="mapping",
                            current_stage="auto_mapping",
                            progress_percent=70,
                            message=(
                                f"Found {len(targeted_mappings)} additional fields via targeted LLM "
                                f"({len(schema_mappings)} schema total)"
                            )
                        )

                    if schema_tables:
                        logger.info(
                            f"🎯 Stage 2: {len(schema_tables)} schema tables → targeted LLM"
                        )
                        tracker.update_progress(
                            status="mapping",
                            current_stage="auto_mapping",
                            progress_percent=70,
                            message=f"Extracting values for {len(schema_tables)} schema tables..."
                        )

                        targeted_table_values = {}
                        table_batches: Dict[str, List[Dict[str, Any]]] = {}
                        for table_def in schema_tables:
                            table_id = table_def.get("id")
                            if not table_id:
                                continue
                            batch_key = _get_table_batch_key(table_def)
                            table_batches.setdefault(batch_key, []).append(table_def)

                        # Build context JSON once — identical for every batch (enables Anthropic cache hits)
                        table_context_json: Optional[str] = None
                        if pdf_fields:
                            context_payload = llm_service_targeted._build_table_context_from_pdf_fields(pdf_fields)
                            table_context_json = json.dumps(context_payload, separators=(",", ":"), ensure_ascii=False)
                            logger.info(f"Table context built once: {len(pdf_fields)} fields → {len(table_context_json)} chars")

                        for batch_key, batch_tables in table_batches.items():
                            if not table_context_json:
                                logger.info(f"No pdf_fields available for table batch {batch_key}")
                                continue

                            row_labels_by_table: Dict[str, List[str]] = {}

                            for table_def in batch_tables:
                                table_id = table_def.get("id")
                                if not table_id:
                                    continue
                                row_labels = schema_table_row_labels.get(table_id, {}).get("row_labels", [])
                                if row_labels and all(not str(lbl).strip() for lbl in row_labels):
                                    logger.info(
                                        f"Row labels empty for table {table_id}; using row_index order"
                                    )
                                    row_labels = []
                                row_labels_by_table[table_id] = row_labels

                            logger.info(
                                f"Table batch extraction: batch={batch_key} tables={len(batch_tables)}"
                            )

                            batch_result = asyncio.run(
                                llm_service_targeted.extract_schema_table_values_rag_batch(
                                    batch_tables,
                                    pdf_fields,
                                    row_labels_by_table=row_labels_by_table,
                                    prebuilt_context_json=table_context_json,
                                )
                            )
                            if batch_result:
                                targeted_table_values.update(batch_result)

                        targeted_table_mappings = mapping_coordinator.create_targeted_schema_table_mappings(
                            schema_tables, targeted_table_values, schema_table_row_labels
                        )

                        for mapping in targeted_table_mappings:
                            extracted_value = mapping.get("extracted_value")
                            if extracted_value is None:
                                continue
                            pdf_fields.append({
                                "id": mapping.get("pdf_field_id"),
                                "name": mapping.get("pdf_field_name"),
                                "type": mapping.get("data_type", "text"),
                                "extracted_value": extracted_value,
                                "confidence": mapping.get("confidence", 0.7),
                                "citations": normalize_citations(mapping.get("citations", [])),
                                "reasoning": mapping.get("reasoning"),
                                "source": "targeted_schema",
                            })

                        schema_mappings = schema_mappings + targeted_table_mappings

                        tracker.update_progress(
                            status="mapping",
                            current_stage="auto_mapping",
                            progress_percent=70,
                            message=(
                                f"Found {len(targeted_table_mappings)} table cells via targeted LLM "
                                f"({len(schema_mappings)} schema total)"
                            )
                        )

                    if not unmapped_fields and not schema_tables:
                        logger.info("All YAML schema fields matched in Stage 1 — skipping Stage 2")
                        tracker.update_progress(
                            status="mapping",
                            current_stage="auto_mapping",
                            progress_percent=70,
                            message=f"All schema fields matched ({len(schema_mappings)} total)"
                        )
            except Exception as e:
                logger.warning(f"Stage 2 targeted mapping failed (continuing to Stage 3): {e}")

        # === STEP 2: Generic + LLM mapping for remaining cells (unless skip_generic_mapping) ===
        llm_service = None
        if not skip_generic_mapping:
            # Get cells already mapped by schema (Stage 1 + Stage 2)
            schema_mapped_cells = mapping_coordinator.get_schema_mapped_cells(schema_mappings)

            # Filter Excel schema to exclude schema-mapped cells
            filtered_excel_schema = mapping_coordinator.filter_generic_schema(
                excel_schema,
                schema_mapped_cells
            )

            # Only run LLM if there are unmapped cells
            if filtered_excel_schema:
                # Initialize LLM service
                llm_service = TemplateFillLLMService(
                    prompt_version=settings.re_template_prompt_version,
                    capture_io_log=settings.capture_llm_io_log,
                    fill_run_id=fill_run_id,
                )

                # Progress callback for batch processing
                def on_batch_complete(batch_num, total_batches, batch_mappings):
                    """Report progress after each batch is mapped."""
                    # Stage 3 progress: 70% (start) → 85% (end)
                    batch_progress = 70 + int((batch_num / total_batches) * 15)
                    tracker.update_progress(
                        status="mapping",
                        current_stage="auto_mapping",
                        progress_percent=batch_progress,
                        message=f"Mapping remaining cells (batch {batch_num}/{total_batches})..."
                    )
                    # Celery heartbeat: yield between batches to reset heartbeat timer
                    self.update_state(
                        state="PROGRESS",
                        meta={"stage": f"generic_batch_{batch_num}_of_{total_batches}"}
                    )
                    logger.info(f"Batch {batch_num}/{total_batches} mapped: {len(batch_mappings)} fields")

                # Auto-map fields (LLM call) with batching and progress tracking
                start_time = time.time()
                mapping_result = asyncio.run(
                    llm_service.auto_map_fields(
                        pdf_fields=pdf_fields,
                        excel_schema=filtered_excel_schema,
                        on_batch_complete=on_batch_complete
                    )
                )
                elapsed_ms = int((time.time() - start_time) * 1000)

                generic_mappings = mapping_result.get("mappings") or []

                # Extract token usage for observability
                usage = mapping_result.get("usage", {})
                llm_input_tokens = usage.get("input_tokens", 0)
                llm_output_tokens = usage.get("output_tokens", 0)
                llm_cache_read_tokens = usage.get("cache_read_input_tokens", 0)
                llm_cache_write_tokens = usage.get("cache_creation_input_tokens", 0)
                llm_model = usage.get("model", settings.synthesis_llm_model)
                llm_batches = usage.get("total_batches", 1)

                # Calculate cache hit rate (percentage of input tokens read from cache)
                total_effective_input = llm_input_tokens + llm_cache_read_tokens
                llm_cache_hit_rate = (llm_cache_read_tokens / total_effective_input) if total_effective_input > 0 else 0.0

                # Compute LLM cost
                llm_cost = compute_llm_cost(llm_model, llm_input_tokens, llm_output_tokens) if (llm_input_tokens + llm_output_tokens) > 0 else 0.0

                logger.info(
                    f"Generic mapping: {len(generic_mappings)} additional fields mapped | "
                    f"Tokens: input={llm_input_tokens:,}, output={llm_output_tokens:,}, "
                    f"cache_hit_rate={llm_cache_hit_rate:.1%}, cost=${llm_cost:.4f}"
                )
            else:
                logger.info("All cells mapped by schema - skipping generic mapping")
                elapsed_ms = 0
        else:
            logger.info("Schema-only mode - skipping generic mapping")
            elapsed_ms = 0

        # === STEP 3: Merge mappings (schema takes priority) ===
        raw_mappings = mapping_coordinator.merge_mappings(schema_mappings, generic_mappings)

        # Log mapping source breakdown
        schema_count = sum(1 for m in raw_mappings if m.get("source") == "schema")
        generic_count = len(raw_mappings) - schema_count

        logger.info(
            f"Mapping sources: {schema_count} schema (100% accurate), "
            f"{generic_count} generic (LLM)"
        )

        # Deduplicate by Excel cell only - one cell should have one source.
        # Enforce strict tier precedence first, then confidence:
        #   Tier 1 (schema) > Tier 2 (targeted_schema) > Tier 3 (generic LLM)
        # This prevents lower tiers from overriding higher-tier mappings.
        def _tier_priority(mapping: dict) -> int:
            source = mapping.get("source")
            if source == "schema":
                return 3
            if source == "targeted_schema":
                return 2
            return 1

        best_by_cell: dict[str, dict] = {}
        for m in raw_mappings:
            excel_sheet = m.get("excel_sheet", "")
            excel_cell = m.get("excel_cell", "")
            if not excel_sheet or not excel_cell:
                continue

            cell_key = f"{excel_sheet}!{excel_cell}"
            current_best = best_by_cell.get(cell_key)
            current_best_tier = _tier_priority(current_best or {})
            candidate_tier = _tier_priority(m)
            current_best_conf = float((current_best or {}).get("confidence") or 0)
            candidate_conf = float(m.get("confidence") or 0)

            if (
                current_best is None
                or candidate_tier > current_best_tier
                or (candidate_tier == current_best_tier and candidate_conf > current_best_conf)
            ):
                best_by_cell[cell_key] = m

        mappings = list(best_by_cell.values())
        total_mapped_fields = len(mappings)

        # Count unique PDF fields that have at least one mapping
        unique_pdf_fields_mapped = len(set(m.get("pdf_field_id") for m in mappings if m.get("pdf_field_id")))

        # Log deduplication stats
        logger.info(
            f"Mapping deduplication: {len(raw_mappings)} raw → "
            f"{len(mappings)} after cell dedup "
            f"({unique_pdf_fields_mapped} unique PDF fields mapped to {len(mappings)} Excel cells) "
            f"[{schema_count} schema + {len(mappings) - schema_count} generic]"
        )

        # Build mapping_result for logging/UI consumers
        targeted_count = sum(1 for m in mappings if m.get("source") == "targeted_schema")
        generic_count = len(mappings) - schema_count - targeted_count
        mapping_result = {
            "mappings": mappings,
            "total_mapped": total_mapped_fields,
            "schema_mapped_count": schema_count,
            "targeted_schema_count": targeted_count,
            "generic_mapped_count": generic_count,
            "high_confidence_count": sum(1 for m in mappings if m.get("confidence", 0) >= 0.85)
        }

        field_mapping = {
            # Use augmented pdf_fields (includes virtual entries for Stage 2 targeted values)
            "pdf_fields": pdf_fields,
            "mappings": mappings,
        }
        if schema_obj:
            field_mapping["yaml_cell_status"] = _build_yaml_cell_status(schema_obj, mappings)
        if schema_summary:
            field_mapping["schema_summary"] = schema_summary

        # Persist metadata (mapping, token data, completion flag)
        # Progress updates via SSE (JobState)
        metadata_params = {
            "field_mapping": field_mapping,
            "total_fields_mapped": total_mapped_fields,
            "auto_mapped_count": total_mapped_fields,
            "user_edited_count": 0,
            "auto_mapping_completed": True,
        }

        # Add token tracking data if generic mapping was used
        if not skip_generic_mapping and 'llm_cost' in locals():
            metadata_params.update({
                "input_tokens": llm_input_tokens,
                "output_tokens": llm_output_tokens,
                "cache_read_tokens": llm_cache_read_tokens,
                "cache_write_tokens": llm_cache_write_tokens,
                "model_name": llm_model,
                "llm_batches_count": llm_batches,
                "cache_hit_rate": llm_cache_hit_rate,
                "cost_usd": llm_cost,
            })

        metadata_params["status"] = "awaiting_review"
        metadata_params["current_stage"] = "auto_mapping"
        repo.update_fill_run(fill_run_id, **metadata_params)

        db.close()

        logger.info(
            f"Auto-mapping complete: {len(mappings)} Excel cells mapped "
            f"(from {unique_pdf_fields_mapped} unique PDF fields) — "
            f"{schema_count} alias, {targeted_count} targeted LLM, {generic_count} generic LLM"
        )

        # Reuse targeted_count and generic_count already computed above

        # Build user-friendly message
        if schema_count > 0 or targeted_count > 0:
            parts = []
            if schema_count:
                parts.append(f"{schema_count} alias")
            if targeted_count:
                parts.append(f"{targeted_count} targeted LLM")
            if generic_count > 0:
                parts.append(f"{generic_count} generic LLM")
            status_msg = f"Mapped {len(mappings)} cells ({', '.join(parts)})"
        else:
            status_msg = f"Mapped {len(mappings)} cells ({mapping_result.get('high_confidence_count', 0)} high confidence)"

        tracker.update_progress(
            status="awaiting_review",
            current_stage="auto_mapping",
            progress_percent=85,
            message=status_msg
        )

        payload["mapping_result"] = mapping_result
        payload["processing_time_ms"] = payload.get("processing_time_ms", 0) + elapsed_ms
        return {"status": "completed", **payload}

    except SoftTimeLimitExceeded:
        logger.warning(f"auto_map_fields_task soft time limit exceeded for fill_run={fill_run_id}")
        repo.update_fill_run(fill_run_id, status="failed", error_stage="auto_mapping",
                             error_message="Task timed out (soft limit)")
        tracker.mark_error(error_stage="auto_mapping", error_message="Auto-mapping timed out",
                           error_type="timeout", is_retryable=False)
        _reverse_template_fill_shadow(fill_run_id, "auto_mapping_timeout", "auto_mapping")
        db.close()
        return {"status": "failed", "error": "timeout", **payload}

    except Exception as e:
        logger.error(f"Auto-mapping failed: {e}", exc_info=True)

        repo.update_fill_run(
            fill_run_id,
            status="failed",
            error_stage="auto_mapping",
            error_message=str(e)
        )

        tracker.update_progress(
            status="failed",
            current_stage="auto_mapping",
            message=f"Auto-mapping failed: {str(e)}"
        )
        _reverse_template_fill_shadow(fill_run_id, "auto_mapping_failed", "auto_mapping")

        db.close()
        return {"status": "failed", "error": str(e), **payload}


@shared_task(bind=True)
def fill_excel_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fill Excel template with data from Azure DI (extracted_value).

    Phase 5 (LLM extraction) has been removed - we use Azure DI values directly!

    Args:
        payload: {
            "fill_run_id": str,
            "template_id": str,
            "job_id": str
        }

    Returns:
        Updated payload with artifact info
    """
    # Check if previous task failed
    if payload.get("status") == "failed":
        logger.warning(f"Skipping Excel filling because previous task failed: {payload.get('error')}")
        return payload  # Pass through the failed status

    fill_run_id = payload["fill_run_id"]
    template_id = payload["template_id"]
    job_id = payload["job_id"]

    db = _get_db_session()
    repo = TemplateRepository(db)
    tracker = JobProgressTracker(db, job_id)

    # Idempotency guard: skip if already completed (re-queued after worker restart)
    _fill_run_check = repo.get_fill_run(fill_run_id)
    if _fill_run_check and _fill_run_check.status in ("completed", "failed"):
        logger.warning(
            f"fill_excel_task skipped — fill_run={fill_run_id} already in status={_fill_run_check.status!r}"
        )
        db.close()
        return {**payload, "status": _fill_run_check.status}

    # Start latency timer
    start_time = time.monotonic()
    org_id = None

    try:
        logger.info(f"Filling Excel for fill run: {fill_run_id}")

        tracker.update_progress(
            status="filling",
            current_stage="excel_filling",
            progress_percent=90,
            message="Filling Excel template"
        )

        # Get fill run with field mapping
        fill_run = repo.get_fill_run(fill_run_id)
        if not fill_run:
            raise ValueError(f"Fill run not found: {fill_run_id}")

        org_id = fill_run.org_id

        field_mapping = fill_run.field_mapping

        # Get template
        template = repo.get_template(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        # Get file extension from template (e.g., ".xlsx" or ".xlsm")
        file_ext = template.file_extension or ".xlsx"

        # Download template file from storage WITH CORRECT EXTENSION
        storage = get_storage_backend()
        template_local_path = f"/tmp/template_{template_id}{file_ext}"
        storage.download(template.file_path, template_local_path)

        # Prepare output path WITH CORRECT EXTENSION
        output_local_path = f"/tmp/filled_{fill_run_id}{file_ext}"

        # Get extracted_data in clean nested schema format
        # Schema: {
        #   "llm_extracted": {field_id: {...}, ...},
        #   "manual_edits": {sheet_name: {cell_address: {...}, ...}, ...}
        # }
        extracted_data = fill_run.extracted_data or {"llm_extracted": {}, "manual_edits": {}}

        llm_extracted = extracted_data.get("llm_extracted", {})
        manual_edits = extracted_data.get("manual_edits", {})

        # Validate manual_edits structure (protect against data corruption)
        if not isinstance(manual_edits, dict):
            logger.warning(f"manual_edits is not a dict (type: {type(manual_edits)}), resetting to empty dict")
            manual_edits = {}
        else:
            # Ensure all sheet values are dicts (clean up corrupted entries)
            cleaned_manual_edits = {}
            for sheet_name, cells in manual_edits.items():
                if isinstance(cells, dict):
                    cleaned_manual_edits[sheet_name] = cells
                else:
                    logger.warning(f"Skipping corrupted manual_edits entry: {sheet_name} (type: {type(cells)})")
            manual_edits = cleaned_manual_edits

        # Add LLM auto-mapped values as fallback (matches UI getCellValue)
        pdf_fields = field_mapping.get('pdf_fields', [])
        for pdf_field in pdf_fields:
            field_id = pdf_field.get('id')
            auto_mapped_value = pdf_field.get('extracted_value')

            # Only add if not already in llm_extracted (user edits take precedence).
            # Use `is not None` (not truthiness) so empty strings still populate the entry;
            # an empty extracted_value means Azure DI found the key but not the value —
            # the mapping confidence will reflect this via schema_mapper's has_value flag.
            if field_id and field_id not in llm_extracted and auto_mapped_value is not None:
                field_entry = {
                    'value': auto_mapped_value,
                    'confidence': pdf_field.get('confidence', 0.95),
                    'citations': pdf_field.get('citations', []),
                    'user_edited': False
                }
                # Include bbox for PDF highlighting if available
                if 'bbox' in pdf_field:
                    field_entry['bbox'] = pdf_field['bbox']

                llm_extracted[field_id] = field_entry

        user_edited_count = sum(len(cells) for cells in manual_edits.values())
        auto_mapped_count = len(llm_extracted) - sum(1 for data in llm_extracted.values() if data.get('user_edited'))

        # Prepare clean extracted_data for filling
        extracted_data = {
            "llm_extracted": llm_extracted,
            "manual_edits": manual_edits
        }

        logger.info(
            f"Prepared extracted_data for filling: {user_edited_count} user-edited + "
            f"{auto_mapped_count} LLM auto-mapped = {len(llm_extracted)} total"
        )

        # Initialize Excel handler
        handler = ExcelHandler()

        # Fill template
        fill_summary = handler.fill_template(
            template_path=template_local_path,
            output_path=output_local_path,
            field_mapping=field_mapping,
            extracted_data=extracted_data
        )

        # Generate storage key: fills/{YYYY}/{MM}/{DD}/{fill_run_id}_{template_name}_filled{ext}
        # Date-partitioned, consistent with workflow-artifacts. Readable in R2 browser.
        from datetime import datetime as _dt
        _now = _dt.utcnow()
        safe_template_name = template.name.replace("/", "_").replace("\\", "_")
        storage_key = (
            f"fills/{_now.year}/{_now.month:02d}/{_now.day:02d}"
            f"/{fill_run_id}_{safe_template_name}_filled{file_ext}"
        )
        storage.upload(output_local_path, storage_key)

        # Create artifact metadata WITH CORRECT EXTENSION
        artifact = {
            "backend": settings.storage_backend,
            "key": storage_key,
            "size": Path(output_local_path).stat().st_size,
            "filename": f"{safe_template_name}_filled{file_ext}"
        }

        # Update fill run
        repo.update_fill_run(
            fill_run_id,
            artifact=artifact,
            status="completed",
            filling_completed=True,
            completed_at=datetime.utcnow(),
            processing_time_ms=payload.get("processing_time_ms", 0)
        )

        # Record metrics
        record_template_fill_completed(org_id=fill_run.org_id)

        # Record latency
        latency = time.monotonic() - start_time
        try:
            TEMPLATE_FILL_LATENCY_SECONDS.observe(latency)
        except Exception as e:
            logger.warning(f"Failed to record template fill latency: {e}", exc_info=True)

        db.close()

        logger.info(
            f"Excel filling complete: {fill_summary['total_cells_filled']} cells filled"
        )
        commit_shadow_credits(operation_type="template_fill_run", reference_id=fill_run_id)

        # Use mark_completed() to send proper SSE termination events ("complete" + "end")
        # NOT just update_progress() which only sends "progress" event
        # This ensures the SSE stream terminates properly and UI receives completion signal
        tracker.mark_completed()

        payload["artifact"] = artifact
        payload["fill_summary"] = fill_summary
        return {"status": "completed", **payload}

    except SoftTimeLimitExceeded:
        logger.warning(f"fill_excel_task soft time limit exceeded for fill_run={fill_run_id}")
        repo.update_fill_run(fill_run_id, status="failed", error_stage="excel_filling",
                             error_message="Task timed out (soft limit)")
        tracker.mark_error(error_stage="excel_filling", error_message="Excel filling timed out",
                           error_type="timeout", is_retryable=False)
        _reverse_template_fill_shadow(fill_run_id, "excel_filling_timeout", "excel_filling")
        db.close()
        return {"status": "failed", "error": "timeout", **payload}

    except Exception as e:
        logger.error(f"Excel filling failed: {e}", exc_info=True)

        repo.update_fill_run(
            fill_run_id,
            status="failed",
            error_stage="excel_filling",
            error_message=str(e)
        )

        # Record metrics
        record_template_fill_failed(org_id=fill_run.org_id if fill_run else None)

        # Record latency (even for failures)
        latency = time.monotonic() - start_time
        try:
            TEMPLATE_FILL_LATENCY_SECONDS.observe(latency)
        except Exception as e:
            logger.warning(f"Failed to record template fill latency: {e}", exc_info=True)

        # Use mark_error() to send proper SSE termination events ("error" + "end")
        # NOT just update_progress() which only sends "progress" event
        tracker.mark_error(
            error_stage="excel_filling",
            error_message=str(e),
            error_type="fill_error",
            is_retryable=False
        )
        _reverse_template_fill_shadow(fill_run_id, "excel_filling_failed", "excel_filling")

        db.close()
        return {"status": "failed", "error": str(e), **payload}


@shared_task(bind=True)
def start_fill_run_chain(
    self,
    template_id: str,
    document_id: str,
    user_id: str,
    fill_run_name: str | None = None,
) -> str:
    """
    Orchestrate the full template filling pipeline.

    Pipeline:
    1. Detect PDF fields (LLM)
    2. Auto-map to Excel cells (LLM)
    3. Wait for user review/edits (pause point)
    4. Extract data (LLM) - triggered separately after user confirmation
    5. Fill Excel (openpyxl)

    Args:
        template_id: Excel template ID
        document_id: PDF document ID
        user_id: User ID

    Returns:
        Fill run ID
    """
    db = _get_db_session()
    repo = TemplateRepository(db)

    try:
        logger.info(
            f"Starting fill run chain: template={template_id}, document={document_id}"
        )

        # Get template
        template = repo.get_template(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        # Create fill run
        template_snapshot = {
            "name": template.name,
            "description": template.description,
            "schema_metadata": template.schema_metadata,
        }

        fill_run = repo.create_fill_run(
            template_id=template_id,
            document_id=document_id,
            org_id=template.org_id,
            user_id=user_id,
            template_snapshot=template_snapshot,
            name=fill_run_name,
        )

        fill_run_id = fill_run.id

        # Create JobState for progress tracking (linked to fill run)
        job_id = fill_run_id  # Use fill_run_id as job tracking ID
        job_repo = JobRepository()
        job_state = job_repo.create_job(
            entity_type="template_fill_run",
            entity_id=fill_run_id,
            status="queued",
            current_stage="initialization",
            progress_percent=5,
            job_id=job_id
        )
        if not job_state:
            raise ValueError("Failed to create job state for fill run")

        db.close()

        # Build task chain (steps 1-2, then pause for user review)
        # User will trigger steps 3-4 via separate API call after reviewing mappings
        task_chain = chain(
            detect_fields_task.s({
                "fill_run_id": fill_run_id,
                "template_id": template_id,
                "document_id": document_id,
                "job_id": job_id,
            }),
            auto_map_fields_task.s(),
        )

        # Execute chain
        task_chain.apply_async(queue='critical')

        logger.info(f"Fill run chain started: {fill_run_id} (queue=critical)")

        return fill_run_id

    except Exception as e:
        logger.error(f"Failed to start fill run chain: {e}", exc_info=True)
        db.close()
        raise


@shared_task(bind=True)
def continue_fill_run_chain(
    self,
    fill_run_id: str,
    job_id: str,
) -> Dict[str, Any]:
    """
    Continue fill run pipeline after user has reviewed mappings.

    Phase 5 (LLM extraction) has been removed!
    This now executes only step 3:
    3. Fill Excel template (openpyxl) using Azure DI sample values

    Args:
        fill_run_id: Fill run ID
        job_id: Job tracking ID

    Returns:
        Final result with artifact
    """
    db = _get_db_session()
    repo = TemplateRepository(db)
    tracker = JobProgressTracker(db, job_id)

    try:
        logger.info(f"Continuing fill run: {fill_run_id}")

        # Get fill run
        fill_run = repo.get_fill_run(fill_run_id)
        if not fill_run:
            raise ValueError(f"Fill run not found: {fill_run_id}")

        # Mark user review as completed
        repo.update_fill_run(
            fill_run_id,
            user_review_completed=True,
            status="filling"  # Go directly to filling (skip extraction)
        )

        db.close()

        # Execute fill task directly (no extraction needed!)
        # Phase 5 removed - we use Azure DI extracted_value directly
        fill_excel_task.apply_async(
            kwargs={
                "payload": {
                    "fill_run_id": fill_run_id,
                    "template_id": fill_run.template_id,
                    "job_id": job_id,
                }
            }
        )

        logger.info(f"Fill run continuation started (direct to filling): {fill_run_id}")

        return {"fill_run_id": fill_run_id, "status": "processing"}

    except Exception as e:
        logger.error(f"Failed to continue fill run: {e}", exc_info=True)

        tracker.update_progress(
            status="failed",
            current_stage="continuation",
            message=f"Failed to continue fill run: {str(e)}"
        )
        _reverse_template_fill_shadow(fill_run_id, "continue_fill_failed", "continuation")

        db.close()
        raise
