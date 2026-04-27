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


def build_chunk_context(chunks: list, source_index: int) -> str:
    """Format chunks as a context string with [SN:pP] citation headers."""
    parts: list[str] = []
    for chunk in chunks:
        bbox_page = chunk.chunk_metadata.get("bbox", {}).get("page") if chunk.chunk_metadata else None
        page = bbox_page or chunk.page_number or "?"
        citation = f"[S{source_index}:p{page}]"

        if getattr(chunk, "section_type", None) == "table":
            chunk_type = "Table Chunk"
        elif getattr(chunk, "section_type", None) == "key_value_pairs":
            chunk_type = "KV Pair"
        else:
            chunk_type = "Narrative"

        parts.append(f"{citation} ({chunk_type})\n{chunk.text}")
    return "\n\n".join(parts)


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

    if total_chars <= settings.re_uw_full_text_max_chars:
        return _direct_extract(run_id, job_id, doc_type, chunks, service, source_index, document_id)
    else:
        return _map_reduce_extract(run_id, job_id, doc_type, chunks, service, source_index, document_id)


def _build_citation_context(chunks: list, source_index: int, document_id: str) -> dict:
    """Build 'S{n}:p{page}' → {page, filename, document_id, source_index, bbox} lookup from chunks."""
    ctx: dict = {}
    for chunk in chunks:
        bbox = chunk.chunk_metadata.get("bbox", {}) if chunk.chunk_metadata else {}
        bbox_page = bbox.get("page") if isinstance(bbox, dict) else None
        page = bbox_page or chunk.page_number or 1
        key = f"S{source_index}:p{page}"
        if key not in ctx:
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
) -> ExtractedDocResult:
    """Single LLM call for docs under the char threshold."""
    context = build_chunk_context(chunks, source_index)
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
        result = ExtractedDocResult(
            run_id=run_id, job_id=job_id, doc_type=doc_type,
            field_citations=field_citations, citation_context=citation_context,
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
        return ExtractedDocResult(run_id=run_id, job_id=job_id, doc_type=doc_type, error=str(e)[:500])


def _map_reduce_extract(
    run_id: str,
    job_id: str,
    doc_type: str,
    chunks: list,
    service: "REExtractionLLMService",
    source_index: int,
    document_id: str = "",
) -> ExtractedDocResult:
    """Phase 1 batch condensation + Phase 2 schema fitting."""
    batches = batch_chunks_by_chars(chunks, settings.re_uw_map_reduce_max_chars_per_batch)
    logger.info(f"Map-reduce: {len(batches)} batches for {doc_type}", extra={"run_id": run_id})
    citation_context = _build_citation_context(chunks, source_index, document_id)

    all_fields: list[dict] = []
    for i, batch in enumerate(batches):
        context = build_chunk_context(batch, source_index)
        condensed: CondensedBatchExtraction = service.condense_batch(context)
        all_fields.extend([f.model_dump() for f in condensed.fields])
        logger.debug(f"Batch {i+1}/{len(batches)}: {len(condensed.fields)} fields condensed")

    extracted = service.reduce_to_schema(doc_type, all_fields, build_chunk_context(chunks, source_index))
    scalars = extracted.get("scalars", {})
    raw_citations = extracted.get("field_citations", {})

    typed = _parse_extraction(doc_type, scalars)
    field_citations = {
        field: {"doc_type": doc_type, **cdata}
        for field, cdata in raw_citations.items()
    }
    result = ExtractedDocResult(
        run_id=run_id, job_id=job_id, doc_type=doc_type,
        field_citations=field_citations, citation_context=citation_context,
    )
    if doc_type == "om":
        result.om = typed
    elif doc_type == "t12":
        result.t12 = typed
    else:
        result.rent_roll = typed
    return result
