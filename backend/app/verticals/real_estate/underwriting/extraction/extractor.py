"""Two-tier document extraction for RE underwriting.

- Direct path: docs <= re_uw_full_text_max_chars → one LLM call
- Map-reduce path: larger docs → Phase 1 batches + Phase 2 reduce
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import settings
from app.utils.logging import logger

if TYPE_CHECKING:
    from .llm_service import REExtractionLLMService

from .schemas import (
    CondensedBatchExtraction,
    ExtractedDocResult,
    OMExtraction,
    RentRollExtraction,
    T12Extraction,
)
from .om_context_selector import select_om_context_chunks
from .t12_table_totals import (
    T12TotalsResult,
    compute_t12_table_totals,
    reconcile_t12_with_computed_totals,
)

def batch_chunks_by_chars(
    chunks: list,
    max_chars: int,
) -> list[list]:
    """Split chunks into batches where each batch stays under max_chars.

    An oversized single chunk is placed in its own batch rather than dropped.
    """
    if not chunks:
        return []
    batches: list[list] = []
    current: list = []
    current_chars = 0
    for chunk in chunks:
        n = len(chunk.text)
        if current_chars + n > max_chars and current:
            batches.append(current)
            current, current_chars = [], 0
        current.append(chunk)
        current_chars += n
    if current:
        batches.append(current)
    return batches


def _build_source_token(chunk, source_index: int) -> str:
    metadata = chunk.chunk_metadata or {}
    if metadata.get("source_kind") == "spreadsheet":
        sheet_name = metadata.get("sheet_name") or "Sheet"
        row_start = metadata.get("row_start")
        row_end = metadata.get("row_end")
        if row_start and row_end:
            return f"S{source_index}:{sheet_name}!R{row_start}-R{row_end}"
        return f"S{source_index}:{sheet_name}"

    bbox_page = metadata.get("bbox", {}).get("page") if metadata else None
    page = bbox_page or chunk.page_number or "?"
    return f"S{source_index}:p{page}"


def build_chunk_context(chunks: list, source_index: int) -> str:
    """Format chunks as a context string with source citation headers."""
    parts: list[str] = []
    for chunk in chunks:
        citation = _build_source_token(chunk, source_index)

        if getattr(chunk, "section_type", None) == "table":
            chunk_type = "Table Chunk"
        elif getattr(chunk, "section_type", None) == "key_value_pairs":
            chunk_type = "KV Pair"
        else:
            chunk_type = "Narrative"

        parts.append(f"[{citation}] ({chunk_type})\n{chunk.text}")
    return "\n\n".join(parts)


def _build_extraction_context(
    chunks: list,
    source_index: int,
    t12_totals: T12TotalsResult | None = None,
) -> str:
    """Format source context, optionally prepending verified T-12 row math."""
    context = build_chunk_context(chunks, source_index)
    if t12_totals and t12_totals.prompt_block:
        return f"{t12_totals.prompt_block}\n\n{context}"
    return context


def _parse_extraction(doc_type: str, data: dict):
    """Convert raw LLM dict into the correct typed extraction model."""
    try:
        if doc_type == "om":
            return OMExtraction(**data)
        elif doc_type == "t12":
            return T12Extraction(**data)
        else:
            return RentRollExtraction(**data)
    except Exception as e:
        logger.warning(f"Extraction schema parse failed for {doc_type}: {e}")
        return None


def _non_null_scalar_count(model) -> int:
    if model is None:
        return 0
    data = model.model_dump(exclude={"unit_mix", "rent_comps", "lease_records"})
    return sum(value not in (None, [], {}) for value in data.values())


def _om_needs_full_context_retry(result: ExtractedDocResult) -> tuple[bool, list[str]]:
    """Return whether selected-context OM extraction should retry full context."""
    reasons: list[str] = []
    om = result.om
    if result.error:
        reasons.append("selected_extraction_error")
        return True, reasons
    if om is None:
        reasons.append("missing_om_payload")
        return True, reasons
    if om.purchase_price is None:
        reasons.append("missing_purchase_price")
    if om.num_units is None and om.rentable_sqft is None:
        reasons.append("missing_units_or_sqft")
    if all(
        value is None
        for value in (
            om.gpr_annual_projected,
            om.noi_year_one_stated,
            om.noi_current_stated,
            om.noi_projected,
        )
    ):
        reasons.append("missing_income_basis")
    non_null_scalars = _non_null_scalar_count(om)
    if non_null_scalars < 8:
        reasons.append("low_field_coverage")
    if len(result.field_citations or {}) < 3:
        reasons.append("low_citation_coverage")
    return bool(reasons), reasons


def extract_document(
    run_id: str,
    job_id: str,
    doc_type: str,
    chunks: list,
    service: "REExtractionLLMService",
    source_index: int = 1,
    document_id: str = "",
) -> ExtractedDocResult:
    """Extract structured data from one document's chunks.

    Chooses direct or map-reduce path based on total char count.
    source_index: the S-number used in [SN:pP] citation tokens (1-based).
    document_id: stored in citation_context for frontend PDF navigation.
    """
    total_chars = sum(len(c.text) for c in chunks)
    logger.info(
        f"Extracting {doc_type} ({len(chunks)} chunks, {total_chars:,} chars)",
        extra={"run_id": run_id, "doc_type": doc_type},
    )

    t12_totals = compute_t12_table_totals(chunks, source_index) if doc_type == "t12" else None

    if (
        doc_type == "om"
        and settings.re_uw_om_context_selector_enabled
        and total_chars > settings.re_uw_om_context_selector_min_chars
    ):
        selection = select_om_context_chunks(
            chunks,
            source_index=source_index,
            max_chars=settings.re_uw_om_context_max_chars,
        )
        logger.info(
            "OM context selector: "
            f"{selection.metadata.get('selected_chunk_count', 0)}/"
            f"{selection.metadata.get('original_chunk_count', 0)} chunks, "
            f"{selection.metadata.get('selected_char_count', 0):,}/"
            f"{selection.metadata.get('original_char_count', 0):,} chars",
            extra={"run_id": run_id, "doc_type": doc_type},
        )
        selected_result = _direct_extract(
            run_id,
            job_id,
            doc_type,
            selection.selected_chunks or chunks,
            service,
            source_index,
            document_id,
            t12_totals,
            extraction_metadata={"om_context_selection": selection.metadata},
        )
        should_retry, retry_reasons = _om_needs_full_context_retry(selected_result)
        if should_retry:
            fallback_metadata = {
                **selection.metadata,
                "fallback_to_full_context": True,
                "fallback_reasons": retry_reasons,
            }
            logger.warning(
                "OM selected-context extraction fell back to full context: "
                + ", ".join(retry_reasons),
                extra={"run_id": run_id, "doc_type": doc_type},
            )
            fallback_result = _direct_extract(
                run_id,
                job_id,
                doc_type,
                chunks,
                service,
                source_index,
                document_id,
                t12_totals,
                extraction_metadata={"om_context_selection": fallback_metadata},
            )
            return fallback_result
        return selected_result

    if total_chars <= settings.re_uw_full_text_max_chars:
        return _direct_extract(
            run_id,
            job_id,
            doc_type,
            chunks,
            service,
            source_index,
            document_id,
            t12_totals,
        )
    return _map_reduce_extract(
        run_id,
        job_id,
        doc_type,
        chunks,
        service,
        source_index,
        document_id,
        t12_totals,
    )


def _build_citation_context(chunks: list, source_index: int, document_id: str) -> dict:
    """Build source token → citation metadata lookup from chunks."""
    ctx: dict = {}
    for chunk in chunks:
        metadata = chunk.chunk_metadata or {}
        key = _build_source_token(chunk, source_index)
        if key in ctx:
            continue

        if metadata.get("source_kind") == "spreadsheet":
            ctx[key] = {
                "page": None,
                "filename": getattr(chunk, "source_filename", "") or "",
                "document_id": document_id,
                "source_index": source_index,
                "bbox": None,
                "source_kind": "spreadsheet",
                "sheet_name": metadata.get("sheet_name"),
                "row_start": metadata.get("row_start"),
                "row_end": metadata.get("row_end"),
                "source_text": chunk.text[:1000],
            }
            continue

        bbox = metadata.get("bbox", {})
        bbox_page = bbox.get("page") if isinstance(bbox, dict) else None
        page = bbox_page or chunk.page_number or 1
        normalized_bbox = None
        if isinstance(bbox, dict) and bbox:
            normalized_bbox = {
                **bbox,
                "page": bbox_page or page,
            }
        ctx[key] = {
            "page": page,
            "filename": getattr(chunk, "source_filename", "") or "",
            "document_id": document_id,
            "source_index": source_index,
            "bbox": normalized_bbox,
        }
    return ctx


def _direct_extract(
    run_id: str,
    job_id: str,
    doc_type: str,
    chunks: list,
    service: "REExtractionLLMService",
    source_index: int,
    document_id: str = "",
    t12_totals: T12TotalsResult | None = None,
    extraction_metadata: dict | None = None,
) -> ExtractedDocResult:
    """Single LLM call for docs under the char threshold."""
    context = _build_extraction_context(chunks, source_index, t12_totals)
    citation_context = _build_citation_context(chunks, source_index, document_id)
    try:
        if doc_type == "om":
            extracted = service.extract_om(context)
        elif doc_type == "t12":
            extracted = service.extract_t12(context)
        else:
            extracted = service.extract_rent_roll(context)

        scalars = extracted.get("scalars", {})
        raw_citations = extracted.get("field_citations", {})

        typed = _parse_extraction(doc_type, scalars)
        field_citations = {
            field: {"doc_type": doc_type, **cdata}
            for field, cdata in raw_citations.items()
        }
        result_metadata = dict(extraction_metadata or {})
        if doc_type == "t12" and t12_totals is not None:
            t12_metadata = reconcile_t12_with_computed_totals(
                t12=typed,
                field_citations=field_citations,
                totals_result=t12_totals,
                run_id=run_id,
            )
            if t12_metadata.get("computed_from_spreadsheet"):
                result_metadata["t12_table_totals"] = t12_metadata
        result = ExtractedDocResult(
            run_id=run_id, job_id=job_id, doc_type=doc_type,
            field_citations=field_citations, citation_context=citation_context,
            extraction_metadata=result_metadata,
        )
        if doc_type == "om":
            result.om = typed
        elif doc_type == "t12":
            result.t12 = typed
        else:
            result.rent_roll = typed
        return result
    except Exception as e:
        logger.error(f"Direct extraction failed for {doc_type}: {e}", extra={"run_id": run_id})
        return ExtractedDocResult(
            run_id=run_id,
            job_id=job_id,
            doc_type=doc_type,
            error=str(e)[:500],
            extraction_metadata=dict(extraction_metadata or {}),
        )


def _map_reduce_extract(
    run_id: str,
    job_id: str,
    doc_type: str,
    chunks: list,
    service: "REExtractionLLMService",
    source_index: int,
    document_id: str = "",
    t12_totals: T12TotalsResult | None = None,
) -> ExtractedDocResult:
    """Phase 1 batch condensation + Phase 2 schema fitting."""
    batches = batch_chunks_by_chars(chunks, settings.re_uw_map_reduce_max_chars_per_batch)
    logger.info(f"Map-reduce: {len(batches)} batches for {doc_type}", extra={"run_id": run_id})
    citation_context = _build_citation_context(chunks, source_index, document_id)

    all_fields: list[dict] = []
    for i, batch in enumerate(batches):
        context = _build_extraction_context(batch, source_index, t12_totals)
        condensed: CondensedBatchExtraction = service.condense_batch(context)
        all_fields.extend([f.model_dump() for f in condensed.fields])
        logger.debug(f"Batch {i+1}/{len(batches)}: {len(condensed.fields)} fields condensed")

    extracted = service.reduce_to_schema(
        doc_type,
        all_fields,
        _build_extraction_context(chunks, source_index, t12_totals),
    )
    scalars = extracted.get("scalars", {})
    raw_citations = extracted.get("field_citations", {})

    typed = _parse_extraction(doc_type, scalars)
    field_citations = {
        field: {"doc_type": doc_type, **cdata}
        for field, cdata in raw_citations.items()
    }
    extraction_metadata = {}
    if doc_type == "t12" and t12_totals is not None:
        t12_metadata = reconcile_t12_with_computed_totals(
            t12=typed,
            field_citations=field_citations,
            totals_result=t12_totals,
            run_id=run_id,
        )
        if t12_metadata.get("computed_from_spreadsheet"):
            extraction_metadata["t12_table_totals"] = t12_metadata
    result = ExtractedDocResult(
        run_id=run_id, job_id=job_id, doc_type=doc_type,
        field_citations=field_citations, citation_context=citation_context,
        extraction_metadata=extraction_metadata,
    )
    if doc_type == "om":
        result.om = typed
    elif doc_type == "t12":
        result.t12 = typed
    else:
        result.rent_roll = typed
    return result
