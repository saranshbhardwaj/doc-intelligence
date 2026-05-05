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


def _chunk_page_number(chunk) -> int | None:
    metadata = chunk.chunk_metadata or {}
    bbox = metadata.get("bbox")
    if isinstance(bbox, dict) and bbox.get("page") is not None:
        try:
            return int(bbox["page"])
        except (TypeError, ValueError):
            pass
    page = getattr(chunk, "page_number", None)
    if page is None:
        page = metadata.get("page_number")
    if page is None:
        return None
    try:
        return int(page)
    except (TypeError, ValueError):
        return None


def _chunk_section_type(chunk) -> str:
    return str(getattr(chunk, "section_type", None) or "").lower()


_OM_FINANCIAL_TABLE_KEYWORDS = (
    "operating statement",
    "income statement",
    "financial",
    "revenue",
    "income",
    "expense",
    "noi",
    "net operating income",
    "gross potential rent",
    "gpr",
    "current",
    "year 1",
    "year-one",
    "pro forma",
    "stabilized",
)

_OM_DEMOGRAPHIC_KEYWORDS = (
    "demographic",
    "population",
    "household income",
    "average household income",
    "storage sqft",
    "square feet per capita",
)

_OM_DEMOGRAPHIC_RADIUS_KEYWORDS = (
    "3 mile",
    "3-mile",
    "3 miles",
    "3-miles",
    "within 3",
    "1 mile | 3 miles | 5 miles",
    "1 mile 3 miles 5 miles",
)

_OM_MARKET_COMPETITION_KEYWORDS = (
    "competition",
    "competitive",
    "competitor",
    "nearby",
    "facility",
    "rent comp",
    "rent comparable",
    "storage supply",
)


def _is_om_targeted_chunk(chunk) -> bool:
    return _chunk_section_type(chunk) in {"table", "key_value_pairs", "key_value"}


def _chunk_haystack(chunk) -> str:
    metadata = chunk.chunk_metadata or {}
    pieces = [
        str(getattr(chunk, "text", "") or ""),
        str(getattr(chunk, "section_heading", "") or ""),
        str(metadata.get("section_heading") or ""),
        str(metadata.get("table_name") or ""),
        " ".join(str(item) for item in (metadata.get("column_headers") or [])),
    ]
    return "\n".join(piece for piece in pieces if piece).lower()


def _has_any_keyword(haystack: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in haystack for keyword in keywords)


def _is_om_table_chunk(chunk) -> bool:
    return _chunk_section_type(chunk) == "table"


def _is_om_financial_table_chunk(chunk) -> bool:
    return _is_om_table_chunk(chunk) and _has_any_keyword(
        _chunk_haystack(chunk),
        _OM_FINANCIAL_TABLE_KEYWORDS,
    )


def _is_om_demographic_market_haystack(haystack: str) -> bool:
    has_demographics = _has_any_keyword(haystack, _OM_DEMOGRAPHIC_KEYWORDS)
    has_radius = _has_any_keyword(haystack, _OM_DEMOGRAPHIC_RADIUS_KEYWORDS)
    has_market_competition = _has_any_keyword(haystack, _OM_MARKET_COMPETITION_KEYWORDS)

    if has_demographics:
        return has_radius or has_market_competition
    return has_market_competition


def _is_om_demographic_market_chunk(chunk) -> bool:
    return _is_om_demographic_market_haystack(_chunk_haystack(chunk))


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


def _om_increment_reason_count(reason_counts: dict[str, int], reason: str) -> None:
    reason_counts[reason] = reason_counts.get(reason, 0) + 1


def _build_om_two_call_contexts(chunks: list, source_index: int) -> tuple[str, str, dict]:
    """Build split OM contexts: structure tables first, extraction evidence second."""
    full_context = build_chunk_context(chunks, source_index)
    table_indexes: set[int] = set()
    financial_table_indexes: set[int] = set()
    page_one_indexes: set[int] = set()
    kv_indexes: set[int] = set()
    demographic_market_indexes: set[int] = set()

    for index, chunk in enumerate(chunks):
        section_type = _chunk_section_type(chunk)
        page_number = _chunk_page_number(chunk)
        haystack = _chunk_haystack(chunk)
        is_table = section_type == "table"

        if is_table:
            table_indexes.add(index)
            if _has_any_keyword(haystack, _OM_FINANCIAL_TABLE_KEYWORDS):
                financial_table_indexes.add(index)
        if page_number == 1:
            page_one_indexes.add(index)
        if section_type in {"key_value_pairs", "key_value"}:
            kv_indexes.add(index)
        if _is_om_demographic_market_haystack(haystack):
            demographic_market_indexes.add(index)

    structure_indexes = sorted(financial_table_indexes or table_indexes)
    extraction_indexes = sorted(
        page_one_indexes | kv_indexes | table_indexes | demographic_market_indexes
    )
    structure_used_fallback = not bool(structure_indexes)
    extraction_used_fallback = not bool(extraction_indexes)

    structure_selected_indexes = range(len(chunks)) if structure_used_fallback else structure_indexes
    extraction_selected_indexes = range(len(chunks)) if extraction_used_fallback else extraction_indexes
    structure_chunks = [chunks[index] for index in structure_selected_indexes]
    extraction_chunks = [chunks[index] for index in extraction_selected_indexes]
    structure_context = (
        full_context
        if structure_used_fallback
        else build_chunk_context(structure_chunks, source_index)
    )
    extraction_context = (
        full_context
        if extraction_used_fallback
        else build_chunk_context(extraction_chunks, source_index)
    )

    structure_reason_counts: dict[str, int] = {}
    for chunk in structure_chunks:
        if _is_om_financial_table_chunk(chunk):
            _om_increment_reason_count(structure_reason_counts, "financial_table")
        elif _is_om_table_chunk(chunk):
            _om_increment_reason_count(structure_reason_counts, "table")
        else:
            _om_increment_reason_count(structure_reason_counts, "fallback")

    extraction_reason_counts: dict[str, int] = {}
    for chunk in extraction_chunks:
        reasons: list[str] = []
        if _chunk_page_number(chunk) == 1:
            reasons.append("page_one")
        if _chunk_section_type(chunk) in {"key_value_pairs", "key_value"}:
            reasons.append("kv")
        if _is_om_table_chunk(chunk):
            reasons.append("table")
        if _is_om_demographic_market_chunk(chunk):
            reasons.append("demographic_market")
        _om_increment_reason_count(
            extraction_reason_counts,
            "+".join(reasons) if reasons else "fallback",
        )

    metadata = {
        "enabled": True,
        "source": "split_contexts",
        "original_chunk_count": len(chunks),
        "structure_chunk_count": len(structure_chunks),
        "extraction_chunk_count": len(extraction_chunks),
        "structure_char_count": len(structure_context),
        "extraction_char_count": len(extraction_context),
        "structure_used_fallback": structure_used_fallback,
        "extraction_used_fallback": extraction_used_fallback,
        "structure_source_tokens": [
            _build_source_token(chunk, source_index) for chunk in structure_chunks
        ],
        "extraction_source_tokens": [
            _build_source_token(chunk, source_index) for chunk in extraction_chunks
        ],
        "structure_reason_counts": structure_reason_counts,
        "extraction_reason_counts": extraction_reason_counts,
    }
    return structure_context, extraction_context, metadata


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

    if doc_type == "om" and settings.re_uw_om_two_call_enabled:
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
        om_context_metadata = None
        if doc_type == "om":
            if settings.re_uw_om_two_call_enabled:
                (
                    structure_context,
                    extraction_context,
                    om_context_metadata,
                ) = _build_om_two_call_contexts(chunks, source_index)
                logger.info(
                    "OM two-call contexts: structure_chunks=%s extraction_chunks=%s "
                    "structure_chars=%s extraction_chars=%s structure_reasons=%s "
                    "extraction_reasons=%s",
                    om_context_metadata["structure_chunk_count"],
                    om_context_metadata["extraction_chunk_count"],
                    om_context_metadata["structure_char_count"],
                    om_context_metadata["extraction_char_count"],
                    om_context_metadata["structure_reason_counts"],
                    om_context_metadata["extraction_reason_counts"],
                    extra={"run_id": run_id, "doc_type": doc_type},
                )
                extracted = service.extract_om(
                    extraction_context,
                    structure_context=structure_context,
                )
            else:
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
        if doc_type == "om" and om_context_metadata is not None:
            result_metadata["om_two_call_contexts"] = om_context_metadata
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
