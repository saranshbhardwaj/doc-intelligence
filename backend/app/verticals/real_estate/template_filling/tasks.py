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
from typing import Any, Dict

from celery import chain, shared_task
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.repositories.document_repository import DocumentRepository
from app.repositories.job_repository import JobRepository
from app.repositories.template_repository import TemplateRepository
from app.services.artifacts import persist_artifact
from app.services.job_tracker import JobProgressTracker
from app.core.storage.storage_factory import get_storage_backend
from app.utils.costs import compute_llm_cost
from app.utils.logging import logger
from app.verticals.real_estate.template_filling.excel_handler import ExcelHandler
from app.verticals.real_estate.template_filling.llm_service import TemplateFillLLMService
from app.verticals.real_estate.template_filling.excel.mapping_coordinator import coordinator as mapping_coordinator


def _get_db_session() -> Session:
    """Get a new database session."""
    return SessionLocal()


def _infer_field_type(value: str) -> str:
    """
    Infer field type from a value string.

    Returns: text, number, currency, percentage, or date
    """
    if not value:
        return "text"

    value_clean = value.strip().replace(",", "").replace("$", "").replace("%", "")

    # Check for percentage
    if "%" in value:
        return "percentage"

    # Check for currency
    if "$" in value or value.lower().startswith("usd"):
        return "currency"

    # Check for number
    try:
        float(value_clean)
        return "number"
    except ValueError:
        pass

    # Check for date patterns (MM/DD/YYYY, YYYY-MM-DD, etc.)
    import re
    date_patterns = [
        r"\d{1,2}/\d{1,2}/\d{2,4}",
        r"\d{4}-\d{1,2}-\d{1,2}",
        r"\d{1,2}-\d{1,2}-\d{2,4}",
    ]
    for pattern in date_patterns:
        if re.match(pattern, value.strip()):
            return "date"

    return "text"


def _infer_field_type_from_name(name: str) -> str:
    """
    Infer field type from a field/column name.

    Returns: text, number, currency, percentage, or date
    """
    if not name:
        return "text"

    name_lower = name.lower()

    # Currency indicators
    if any(keyword in name_lower for keyword in ["price", "cost", "amount", "revenue", "rent", "fee", "payment", "income", "expense", "value", "$", "usd"]):
        return "currency"

    # Percentage indicators
    if any(keyword in name_lower for keyword in ["rate", "percent", "%", "ratio", "yield", "cap rate", "occupancy"]):
        return "percentage"

    # Date indicators
    if any(keyword in name_lower for keyword in ["date", "year", "month", "day", "time", "period", "expiration", "maturity"]):
        return "date"

    # Number indicators
    if any(keyword in name_lower for keyword in ["count", "number", "total", "quantity", "sf", "sqft", "square", "units", "size", "area", "#"]):
        return "number"

    return "text"


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
        document = document_repo.get_by_id(document_id)
        if not document:
            raise ValueError(f"Document not found: {document_id}")

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

        logger.info(f"Found {len(kv_chunks)} key-value chunks and {len(table_chunks)} table chunks")

        # Process KV chunks
        for chunk, metadata in kv_chunks:
            kv_pairs = metadata.get("key_value_pairs", [])

            for kv in kv_pairs:
                key = kv.get("key", "")
                value = kv.get("value", "")
                confidence = kv.get("confidence", 0.95)
                # Use the INDIVIDUAL KV pair's page number, not the chunk's aggregated page
                kv_page_number = kv.get("page_number") or chunk.page_number
                citation = f"[D1:p{kv_page_number}]"

                if not key:
                    continue

                # Infer field type from value
                field_type = _infer_field_type(value)

                field_data = {
                    "id": f"kv_{field_id_counter}",
                    "name": key,
                    "type": field_type,
                    "sample_value": value or "",
                    "confidence": confidence,
                    "citations": [citation],
                    "description": f"Key-value field from page {kv_page_number}",
                    "source": "key_value_pairs"
                }

                # FIXED: Extract bbox from the INDIVIDUAL KV pair (not chunk-level merged bbox)
                kv_bbox = kv.get("bbox")
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
            table_name = metadata.get("table_name", "")
            column_headers = metadata.get("column_headers", [])
            citation = f"[D1:p{chunk.page_number}]"
            # Extract bbox from chunk metadata for PDF highlighting
            chunk_bbox = metadata.get("bbox")

            for col_header in column_headers:
                if not col_header or col_header.lower() in ["", "none", "n/a"]:
                    continue

                # Try to infer type from column name
                field_type = _infer_field_type_from_name(col_header)

                # Get sample value from first row if available
                sample_value = ""
                table_data = metadata.get("table_data", [])
                if table_data and len(table_data) > 0:
                    # Find column index
                    try:
                        col_idx = column_headers.index(col_header)
                        if col_idx < len(table_data[0]):
                            sample_value = table_data[0][col_idx]
                    except (ValueError, IndexError):
                        pass

                field_data = {
                    "id": f"tbl_{field_id_counter}",
                    "name": col_header,
                    "type": field_type,
                    "sample_value": sample_value,
                    # NOTE: Hardcoded confidence for table columns.
                    # Unlike key-value pairs (which get per-pair confidence from Azure DI),
                    # Azure DI does NOT provide per-column/per-cell confidence for tables.
                    # Future: Could calculate from table structure quality metrics.
                    "confidence": 0.9,
                    "citations": [citation],
                    "description": f"Column from table '{table_name}' on page {chunk.page_number}",
                    "source": "table"
                }

                # Include bbox for PDF highlighting if available
                if chunk_bbox:
                    field_data["bbox"] = chunk_bbox

                # DEBUG: Log first table field's bbox
                if len([f for f in detected_fields if f.get("source") == "table"]) == 0:
                    logger.info(f"[FIELD_DETECTION] First table field: '{col_header}', "
                              f"page={chunk.page_number}, has bbox: {chunk_bbox is not None}, bbox={chunk_bbox}")

                detected_fields.append(field_data)
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

        repo.update_fill_run(
            fill_run_id,
            field_mapping=field_mapping,
            total_fields_detected=len(detected_fields),
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
    use_schema_only = payload.get("use_schema_only", settings.excel_schema_only)
    skip_schema = payload.get("skip_schema", settings.excel_skip_schema)

    db = _get_db_session()
    repo = TemplateRepository(db)
    tracker = JobProgressTracker(db, job_id)

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

        pdf_fields = detection_result.get("fields", [])
        schema_mappings = []
        generic_mappings = []

        # === STEP 1: Try schema-based mapping (unless skipped) ===
        if not skip_schema:
            try:
                from openpyxl import load_workbook

                # Download template file temporarily
                storage = get_storage_backend()
                template_path = storage.download_to_temp(template.file_path)

                # Load workbook for fingerprint check
                workbook = load_workbook(template_path, data_only=False)

                # Identify template
                schema_id = mapping_coordinator.identify_template(workbook)

                if schema_id:
                    logger.info(f"✓ Template identified as: {schema_id}")

                    # Create schema mappings (deterministic, instant)
                    schema_mappings = mapping_coordinator.create_schema_mappings(schema_id, pdf_fields)

                    logger.info(f"Schema mapping: {len(schema_mappings)} fields mapped (confidence=1.0)")

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
                        progress_percent=55,
                        message=f"Schema mapped {len(schema_mappings)} critical fields"
                    )
                else:
                    logger.info("Template not recognized by schema system - will use generic analyzer")

                # Clean up temp file
                Path(template_path).unlink(missing_ok=True)

            except Exception as e:
                logger.warning(f"Schema mapping failed (will fall back to generic): {e}")
                schema_mappings = []

        # === STEP 2: Generic + LLM mapping for remaining cells (unless schema-only mode) ===
        if not use_schema_only:
            # Get cells already mapped by schema
            schema_mapped_cells = mapping_coordinator.get_schema_mapped_cells(schema_mappings)

            # Filter Excel schema to exclude schema-mapped cells
            filtered_excel_schema = mapping_coordinator.filter_generic_schema(
                excel_schema,
                schema_mapped_cells
            )

            # Only run LLM if there are unmapped cells
            if filtered_excel_schema:
                # Initialize LLM service
                llm_service = TemplateFillLLMService()

                # Progress callback for batch processing
                def on_batch_complete(batch_num, total_batches, batch_mappings):
                    """Report progress after each batch is mapped."""
                    # Progress from 60% (start) to 80% (end of mapping)
                    batch_progress = 60 + int((batch_num / total_batches) * 20)
                    tracker.update_progress(
                        status="mapping",
                        current_stage="auto_mapping",
                        progress_percent=batch_progress,
                        message=f"Mapping remaining fields (batch {batch_num}/{total_batches})..."
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

                logger.info(f"Generic mapping: {len(generic_mappings)} additional fields mapped")
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

        # Deduplicate by Excel cell only - one cell should have one source
        # (Keep highest confidence mapping if multiple PDF fields map to the same cell)
        # NOTE: Schema mappings already have confidence=1.0, so they will win ties
        best_by_cell: dict[str, dict] = {}
        for m in raw_mappings:
            excel_sheet = m.get("excel_sheet", "")
            excel_cell = m.get("excel_cell", "")
            if not excel_sheet or not excel_cell:
                continue

            cell_key = f"{excel_sheet}!{excel_cell}"
            current_best = best_by_cell.get(cell_key)
            current_best_conf = float((current_best or {}).get("confidence") or 0)
            candidate_conf = float(m.get("confidence") or 0)

            if current_best is None or candidate_conf > current_best_conf:
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
        mapping_result = {
            "mappings": mappings,
            "total_mapped": total_mapped_fields,
            "schema_mapped_count": schema_count,
            "generic_mapped_count": len(mappings) - schema_count,
            "high_confidence_count": sum(1 for m in mappings if m.get("confidence", 0) >= 0.85)
        }

        field_mapping = {
            "pdf_fields": detection_result.get("fields", []),
            "mappings": mappings
        }

        repo.update_fill_run(
            fill_run_id,
            field_mapping=field_mapping,
            total_fields_mapped=total_mapped_fields,
            auto_mapped_count=total_mapped_fields,
            user_edited_count=0,
            auto_mapping_completed=True,
            status="awaiting_review",
            current_stage="auto_mapping",
        )

        db.close()

        logger.info(
            f"Auto-mapping complete: {len(mappings)} Excel cells mapped "
            f"(from {unique_pdf_fields_mapped} unique PDF fields) - "
            f"{schema_count} via schema (100% accurate), {len(mappings) - schema_count} via LLM"
        )

        # Build user-friendly message
        if schema_count > 0:
            status_msg = f"Mapped {len(mappings)} cells ({schema_count} schema, {len(mappings) - schema_count} LLM)"
        else:
            status_msg = f"Mapped {len(mappings)} cells ({mapping_result.get('high_confidence_count', 0)} high confidence)"

        tracker.update_progress(
            status="awaiting_review",
            current_stage="auto_mapping",
            progress_percent=60,
            message=status_msg
        )

        payload["mapping_result"] = mapping_result
        payload["processing_time_ms"] = payload.get("processing_time_ms", 0) + elapsed_ms
        return {"status": "completed", **payload}

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

        db.close()
        return {"status": "failed", "error": str(e), **payload}


@shared_task(bind=True)
def fill_excel_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fill Excel template with data from Azure DI (sample_value).

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
            auto_mapped_value = pdf_field.get('sample_value')

            # Only add if not already in llm_extracted (user edits take precedence)
            if field_id and field_id not in llm_extracted and auto_mapped_value:
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

        # Upload filled file to storage WITH CORRECT EXTENSION
        storage_key = f"fills/{fill_run_id}{file_ext}"
        storage.upload(output_local_path, storage_key)

        # Create artifact metadata WITH CORRECT EXTENSION
        artifact = {
            "backend": settings.storage_backend,
            "key": storage_key,
            "size": Path(output_local_path).stat().st_size,
            "filename": f"{template.name}_filled{file_ext}"
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

        db.close()

        logger.info(
            f"Excel filling complete: {fill_summary['total_cells_filled']} cells filled"
        )

        # Use mark_completed() to send proper SSE termination events ("complete" + "end")
        # NOT just update_progress() which only sends "progress" event
        # This ensures the SSE stream terminates properly and UI receives completion signal
        tracker.mark_completed()

        payload["artifact"] = artifact
        payload["fill_summary"] = fill_summary
        return {"status": "completed", **payload}

    except Exception as e:
        logger.error(f"Excel filling failed: {e}", exc_info=True)

        repo.update_fill_run(
            fill_run_id,
            status="failed",
            error_stage="excel_filling",
            error_message=str(e)
        )

        # Use mark_error() to send proper SSE termination events ("error" + "end")
        # NOT just update_progress() which only sends "progress" event
        tracker.mark_error(
            error_stage="excel_filling",
            error_message=str(e),
            error_type="fill_error",
            is_retryable=False
        )

        db.close()
        return {"status": "failed", "error": str(e), **payload}


@shared_task(bind=True)
def start_fill_run_chain(
    self,
    template_id: str,
    document_id: str,
    user_id: str,
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
            user_id=user_id,
            template_snapshot=template_snapshot,
        )

        fill_run_id = fill_run.id

        # Create JobState for progress tracking (linked to fill run)
        job_id = fill_run_id  # Use fill_run_id as job tracking ID
        job_repo = JobRepository()
        job_state = job_repo.create_job(
            template_fill_run_id=fill_run_id,
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
        task_chain.apply_async()

        logger.info(f"Fill run chain started: {fill_run_id}")

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
        # Phase 5 removed - we use Azure DI sample_value directly
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

        db.close()
        raise
