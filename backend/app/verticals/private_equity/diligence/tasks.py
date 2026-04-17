"""Celery tasks for PE diligence analysis orchestration."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from celery import shared_task

from app.config import settings
from app.database import SessionLocal
from app.services.job_tracker import JobProgressTracker
from app.utils.logging import logger
from app.verticals.private_equity.diligence.document_classifier import (
    apply_llm_fallback,
    build_low_confidence_inputs,
    classify_documents,
)
from app.verticals.private_equity.diligence.llm_adapter import PEDiligenceClassificationAdapter
from app.verticals.private_equity.diligence.normalization import (
    normalize_evidence_records,
    normalize_llm_financials,
    normalize_summary_payload,
    normalize_findings,
)
from app.verticals.private_equity.diligence.reporting import (
    build_checklist,
    build_checklist_v2,
    build_document_classification_summary,
    build_findings,
    build_summary,
)
from app.verticals.private_equity.diligence.repository import PEDiligenceRepository
from app.verticals.private_equity.diligence.signals import (
    build_numeric_reconciliation_findings,
    extract_clause_hits,
    extract_numeric_signals,
    row_dicts,
)
from app.verticals.private_equity.diligence.verifier import verify_findings


class PipelineCriticalError(Exception):
    """Raised when a pipeline stage fails in a way that makes all subsequent stages useless."""

    def __init__(self, stage: str, message: str):
        self.stage = stage
        super().__init__(message)


@shared_task(bind=True)
def run_diligence_analysis_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    room_id = payload["room_id"]
    run_id = payload["analysis_run_id"]
    job_id = payload.get("job_id")
    user_id = payload["user_id"]
    is_incremental = payload.get("incremental", False)
    added_doc_ids = set(payload.get("added_doc_ids", []))
    removed_doc_ids = set(payload.get("removed_doc_ids", []))
    previous_run_id = payload.get("previous_run_id")

    db = SessionLocal()
    repo = PEDiligenceRepository(db)
    tracker = JobProgressTracker(db, job_id) if job_id else None

    try:
        pipeline_warnings: List[str] = []
        link_results: Dict[str, Any] = {}

        if tracker:
            tracker.update_progress(
                status="running",
                current_stage="load_documents",
                progress_percent=10,
                message="Loading documents...",
            )

        row_data = row_dicts(repo.get_room_documents_and_chunks(room_id=room_id))
        if not row_data:
            raise PipelineCriticalError(
                "load_documents",
                "No indexed document chunks found. Upload and index documents before running analysis.",
            )

        if tracker:
            tracker.update_progress(
                current_stage="document_classification",
                progress_percent=20,
                message=(
                    f"Classifying {len(added_doc_ids)} new documents..."
                    if is_incremental
                    else "Classifying documents..."
                ),
            )

        prev_classifications: Dict[str, dict] = {}
        if is_incremental and previous_run_id:
            prev_run = repo.get_analysis_run(
                room_id=room_id,
                run_id=previous_run_id,
                org_id=payload["org_id"],
                user_id=user_id,
            )
            if prev_run and prev_run.metadata_json:
                prev_classifications = prev_run.metadata_json.get("document_classification", {})

        if is_incremental and prev_classifications:
            added_rows = [row for row in row_data if row["document_id"] in added_doc_ids]
            new_classifications = classify_documents(added_rows) if added_rows else {}
            document_classifications = {
                **{doc_id: cls for doc_id, cls in prev_classifications.items() if doc_id not in removed_doc_ids},
                **new_classifications,
            }
        else:
            document_classifications = classify_documents(row_data)

        llm_rejections: List[dict] = []
        if settings.pe_diligence_classifier_llm_fallback_enabled:
            low_conf_inputs = build_low_confidence_inputs(
                row_data,
                document_classifications,
                max_chars_per_doc=settings.pe_diligence_classifier_llm_input_chars,
            )
            if low_conf_inputs:
                try:
                    adapter = PEDiligenceClassificationAdapter()
                    llm_candidates = asyncio.run(adapter.classify_low_confidence(low_conf_inputs))
                    document_classifications, llm_rejections = apply_llm_fallback(
                        document_classifications,
                        llm_candidates,
                        min_override_confidence=settings.pe_diligence_classifier_llm_min_confidence,
                    )
                except Exception as llm_exc:
                    logger.warning(
                        "PE diligence LLM classification fallback failed; continuing with rule-based output",
                        extra={"room_id": room_id, "run_id": run_id, "error": str(llm_exc)},
                    )
                    pipeline_warnings.append(
                        f"document_classification: LLM fallback failed — {str(llm_exc)[:200]}"
                    )

        if llm_rejections:
            repo.add_audit_events(
                room_id=room_id,
                events=[
                    {
                        "analysis_run_id": run_id,
                        "actor_user_id": user_id,
                        "event_type": "analysis.classification_candidate_rejected",
                        "entity_type": "room_document",
                        "entity_id": rejected.get("document_id"),
                        "payload": {
                            "reason_code": rejected.get("reason_code"),
                            "expected_rule_anchor_id": rejected.get("expected_rule_anchor_id"),
                            "candidate_rule_anchor_id": rejected.get("candidate_rule_anchor_id"),
                            "candidate_confidence": rejected.get("candidate_confidence"),
                        },
                    }
                    for rejected in llm_rejections
                ],
            )

        if not document_classifications:
            raise PipelineCriticalError(
                "document_classification",
                "Document classification produced no results. Check that documents are indexed and contain readable text.",
            )

        classification_summary = build_document_classification_summary(document_classifications)
        repo.bulk_update_room_document_metadata(
            room_id=room_id,
            updates=[
                {
                    "document_id": doc_id,
                    "ingest_status": "classified",
                    "metadata_patch": {"document_classification": classification},
                }
                for doc_id, classification in document_classifications.items()
            ],
        )
        repo.update_analysis_run(
            run_id=run_id,
            metadata_patch={
                "document_classification": document_classifications,
                "document_classification_summary": classification_summary,
            },
        )

        max_link_chars = settings.pe_diligence_amendment_linking_input_chars
        doc_filename_map: Dict[str, str] = {}
        doc_text_head: Dict[str, str] = {}
        for row in row_data:
            document_id = row["document_id"]
            if row.get("filename") and document_id not in doc_filename_map:
                doc_filename_map[document_id] = row["filename"]
            if document_id not in doc_text_head:
                doc_text_head[document_id] = (row.get("text") or "")[:max_link_chars]
            elif len(doc_text_head[document_id]) < max_link_chars:
                doc_text_head[document_id] = (
                    doc_text_head[document_id] + "\n" + (row.get("text") or "")
                )[:max_link_chars]

        room_doc_list = [
            {"document_id": doc_id, "filename": doc_filename_map.get(doc_id, "")}
            for doc_id in document_classifications
        ]

        if tracker:
            tracker.update_progress(
                current_stage="amendment_linking",
                progress_percent=25,
                message="Linking amendments...",
            )

        if settings.pe_diligence_amendment_linking_enabled:
            amendment_docs = [
                {
                    "document_id": doc_id,
                    "filename": doc_filename_map.get(doc_id, ""),
                    "text": doc_text_head.get(doc_id, ""),
                }
                for doc_id, cls in document_classifications.items()
                if cls.get("document_type") == "amendment"
            ]
            if amendment_docs:
                try:
                    from app.verticals.private_equity.diligence.amendment_linker import PEDiligenceAmendmentLinker

                    linker = PEDiligenceAmendmentLinker()
                    link_results = asyncio.run(
                        linker.link_amendments(
                            amendments=amendment_docs,
                            room_documents=room_doc_list,
                        )
                    )
                    repo.bulk_update_room_document_metadata(
                        room_id=room_id,
                        updates=[
                            {
                                "document_id": doc_id,
                                "metadata_patch": {"amendment_link": candidate.model_dump()},
                            }
                            for doc_id, candidate in link_results.items()
                        ],
                    )
                    repo.add_audit_events(
                        room_id=room_id,
                        events=[
                            {
                                "analysis_run_id": run_id,
                                "actor_user_id": user_id,
                                "event_type": (
                                    "amendment.linked" if candidate.parent_document_id else "amendment.unlinked"
                                ),
                                "entity_type": "room_document",
                                "entity_id": doc_id,
                                "payload": candidate.model_dump(),
                            }
                            for doc_id, candidate in link_results.items()
                        ],
                    )
                except Exception as link_exc:
                    logger.warning(
                        "Amendment linking failed; continuing without amendment links",
                        extra={"room_id": room_id, "run_id": run_id, "error": str(link_exc)[:300]},
                    )
                    pipeline_warnings.append(f"amendment_linking: {str(link_exc)[:200]}")

        if tracker:
            tracker.update_progress(
                current_stage="clause_extraction",
                progress_percent=30,
                message="Extracting clauses...",
            )
        clause_hits = extract_clause_hits(row_data)
        structured_clauses_by_type: Dict[str, List[dict]] = {}

        if tracker:
            tracker.update_progress(
                current_stage="numeric_reconciliation",
                progress_percent=48,
                message="Extracting metrics...",
            )
        numeric_signals = extract_numeric_signals(row_data)

        llm_financials: Optional[dict] = None
        if settings.pe_diligence_llm_numeric_extraction_enabled:
            if tracker:
                tracker.update_progress(
                    current_stage="llm_numeric_extraction",
                    progress_percent=55,
                    message="LLM metric extraction...",
                )
            try:
                from app.verticals.private_equity.diligence.numeric_extractor import LLMNumericExtractor

                room_document_ids = list({row["document_id"] for row in row_data if row.get("document_id")})
                llm_financials = asyncio.run(
                    LLMNumericExtractor().extract(
                        db=db,
                        document_ids=room_document_ids,
                        document_classifications=document_classifications,
                        room_id=room_id,
                        run_id=run_id,
                    )
                )
                llm_financials = normalize_llm_financials(llm_financials)
                if llm_financials:
                    repo.update_analysis_run(run_id=run_id, metadata_patch={"llm_financials": llm_financials})
                    logger.info("LLM numeric extraction complete", extra={"room_id": room_id, "run_id": run_id})
            except Exception as num_exc:
                logger.warning(
                    "LLM numeric extraction failed; continuing",
                    extra={"room_id": room_id, "run_id": run_id, "error": str(num_exc)[:300]},
                )
                pipeline_warnings.append(f"llm_numeric_extraction: {str(num_exc)[:200]}")

        checklist_entries: List[dict] = []
        checklist_rows: list = []
        finding_entries: List[dict] = []

        if tracker:
            tracker.update_progress(
                current_stage="per_doc_analysis",
                progress_percent=65,
                message="Analyzing documents...",
            )
        try:
            from app.verticals.private_equity.diligence.findings_synthesizer import LLMFindingsSynthesizer
            from app.verticals.private_equity.diligence.per_doc_analyzer import PerDocumentAnalyzer

            clause_signals_by_doc: Dict[str, List[dict]] = {}
            for hit in clause_hits:
                hit_doc_id = (hit.get("evidence") or {}).get("source_document_id")
                if hit_doc_id:
                    clause_signals_by_doc.setdefault(hit_doc_id, []).append(
                        {
                            "clause_type": hit["clause_type"],
                            "snippet": ((hit.get("evidence") or {}).get("quote") or "")[:200],
                            "page_number": (hit.get("evidence") or {}).get("source_page_number"),
                        }
                    )

            per_doc_filename_map: Dict[str, str] = {
                row["document_id"]: row.get("filename", "")
                for row in row_data
                if row.get("document_id")
            }
            all_doc_ids_with_classifications = {
                doc_id: {**cls, "filename": per_doc_filename_map.get(doc_id, doc_id[:8])}
                for doc_id, cls in document_classifications.items()
            }

            docs_to_analyze = all_doc_ids_with_classifications
            if is_incremental and added_doc_ids:
                docs_to_analyze = {
                    doc_id: cls
                    for doc_id, cls in all_doc_ids_with_classifications.items()
                    if doc_id in added_doc_ids
                }
                logger.info(
                    "Incremental: analyzing only new documents",
                    extra={"room_id": room_id, "added_count": len(docs_to_analyze), "total": len(all_doc_ids_with_classifications)},
                )

            analyzer = PerDocumentAnalyzer(db=db)
            new_per_doc_findings = asyncio.run(
                analyzer.analyze_all_documents(
                    doc_ids_with_classifications=docs_to_analyze,
                    clause_signals_by_doc=clause_signals_by_doc,
                    amendment_links=link_results,
                    room_id=room_id,
                    run_id=run_id,
                )
            )

            per_doc_findings = normalize_findings(list(new_per_doc_findings), source_kind="per_document")
            if is_incremental and previous_run_id:
                prev_findings = repo.list_findings(room_id=room_id)
                unchanged_findings = [
                    {k: v for k, v in finding.__dict__.items() if not k.startswith("_") and k not in ("room_id", "analysis_run_id", "id")}
                    for finding in prev_findings
                    if finding.source_document_id
                    and finding.source_document_id not in added_doc_ids
                    and finding.source_document_id not in removed_doc_ids
                ]
                per_doc_findings.extend(normalize_findings(unchanged_findings, source_kind="historical"))
                per_doc_findings = normalize_findings(per_doc_findings, source_kind="per_document")

            logger.info(
                "Per-doc analysis complete",
                extra={"room_id": room_id, "run_id": run_id, "findings": len(per_doc_findings)},
            )

            structured_clauses_from_perdoc = []
            for finding in per_doc_findings:
                meta = finding.get("metadata_json") or {}
                clause_type = meta.get("clause_type")
                extracted_fields = meta.get("extracted_fields")
                if clause_type and extracted_fields:
                    structured_clauses_from_perdoc.append(
                        {
                            "room_id": room_id,
                            "analysis_run_id": run_id,
                            "source_document_id": finding.get("source_document_id"),
                            "source_chunk_id": finding.get("source_chunk_id"),
                            "source_page_number": finding.get("source_page_number"),
                            "clause_type": clause_type,
                            "playbook_id": meta.get("playbook_slug"),
                            "extracted_fields": extracted_fields,
                            "raw_quote": (finding.get("evidence_quote") or "")[:2000],
                            "interpretation": finding.get("description"),
                            "confidence": finding.get("confidence"),
                            "engine": "per_doc_llm_v2",
                        }
                    )

            seen_clause_keys: dict = {}
            for clause in structured_clauses_from_perdoc:
                key = (clause["source_document_id"], clause["clause_type"])
                existing = seen_clause_keys.get(key)
                if existing is None or (clause.get("confidence") or 0) > (existing.get("confidence") or 0):
                    seen_clause_keys[key] = clause
            structured_clauses_from_perdoc = list(seen_clause_keys.values())

            if structured_clauses_from_perdoc:
                repo.save_clauses(
                    room_id=room_id,
                    run_id=run_id,
                    clauses=structured_clauses_from_perdoc,
                    document_ids=list(added_doc_ids) if is_incremental and added_doc_ids else None,
                )
                logger.info(
                    "Clauses extracted from per-doc findings saved",
                    extra={"room_id": room_id, "run_id": run_id, "count": len(structured_clauses_from_perdoc)},
                )
                for clause in structured_clauses_from_perdoc:
                    structured_clauses_by_type.setdefault(clause["clause_type"], []).append(clause)

            if tracker:
                tracker.update_progress(
                    current_stage="synthesis",
                    progress_percent=82,
                    message="Synthesizing findings...",
                )
            synthesized = asyncio.run(
                LLMFindingsSynthesizer().synthesize_v2(
                    per_doc_findings=per_doc_findings,
                    numeric_signals=numeric_signals,
                    llm_financials=llm_financials,
                    document_classifications=document_classifications,
                    room_id=room_id,
                    run_id=run_id,
                )
            )

            finding_entries = list(per_doc_findings)
            if synthesized:
                finding_entries.extend(normalize_findings(synthesized, source_kind="cross_document_synthesis"))
            finding_entries = normalize_findings(finding_entries, source_kind="pipeline")

            checklist_entries = build_checklist_v2(
                per_doc_findings=per_doc_findings,
                numeric_signals=numeric_signals,
                document_classifications=document_classifications,
                llm_financials=llm_financials,
            )
            checklist_rows = repo.replace_checklist_items(
                room_id=room_id,
                items=[entry["item"] for entry in checklist_entries],
            )
        except Exception as per_doc_exc:
            logger.warning(
                f"Per-doc analysis failed; falling back to rule-based findings: {per_doc_exc!r}",
                extra={"room_id": room_id, "run_id": run_id, "error": str(per_doc_exc)[:300]},
            )
            pipeline_warnings.append(
                f"per_doc_analysis: LLM analysis failed, using rule-based fallback — {str(per_doc_exc)[:200]}"
            )
            checklist_entries = build_checklist(
                row_data,
                clause_hits,
                numeric_signals,
                document_classifications=document_classifications,
                llm_financials=llm_financials,
                structured_clauses_by_type=structured_clauses_by_type,
            )
            checklist_rows = repo.replace_checklist_items(
                room_id=room_id,
                items=[entry["item"] for entry in checklist_entries],
            )
            finding_entries = build_findings(
                row_data,
                clause_hits,
                build_numeric_reconciliation_findings(numeric_signals),
                structured_clauses_by_type=structured_clauses_by_type,
                document_classifications=document_classifications,
            )
            finding_entries = normalize_findings(finding_entries, source_kind="rule_based")

        if tracker:
            tracker.update_progress(
                current_stage="verification",
                progress_percent=86,
                message="Verifying findings...",
            )
        verified_finding_entries, verification_stats = verify_findings(finding_entries)
        repo.update_analysis_run(run_id=run_id, metadata_patch={"verification": verification_stats})

        finding_rows_payload = [
            {key: value for key, value in entry.items() if key != "evidence_list"}
            for entry in verified_finding_entries
        ]
        finding_rows = repo.replace_findings(
            room_id=room_id,
            run_id=run_id,
            findings=finding_rows_payload,
        )

        if tracker:
            tracker.update_progress(
                current_stage="summary_generation",
                progress_percent=90,
                message="Generating summary...",
            )
        room = repo.get_room(room_id=room_id, org_id=payload["org_id"], user_id=user_id)
        summary_payload = build_summary(
            room.name if room else "Diligence Room",
            checklist_entries,
            verified_finding_entries,
            document_classifications,
            verification_stats,
            llm_financials=llm_financials,
        )
        summary_payload = normalize_summary_payload(summary_payload)
        summary_engine = "summary_v2"
        baseline_summary_payload = summary_payload

        if settings.pe_diligence_llm_summary_generation_enabled:
            if tracker:
                tracker.update_progress(
                    current_stage="llm_summary",
                    progress_percent=92,
                    message="LLM summary generation...",
                )
            try:
                from app.verticals.private_equity.diligence.summary_generator import LLMSummaryGenerator

                llm_summary = asyncio.run(
                    LLMSummaryGenerator().generate(
                        room_name=room.name if room else "Diligence Room",
                        finding_entries=verified_finding_entries,
                        checklist_entries=checklist_entries,
                        document_classifications=document_classifications,
                        verification_stats=verification_stats,
                        llm_financials=llm_financials,
                        structured_clauses_by_type=structured_clauses_by_type,
                        room_id=room_id,
                        run_id=run_id,
                    )
                )
                if llm_summary:
                    summary_payload = normalize_summary_payload(llm_summary, fallback=baseline_summary_payload)
                    summary_engine = "llm_summary_v1"
                    logger.info("LLM summary generation complete", extra={"room_id": room_id, "run_id": run_id})
            except Exception as sum_exc:
                logger.warning(
                    "LLM summary generation failed; using template summary",
                    extra={"room_id": room_id, "run_id": run_id, "error": str(sum_exc)[:300]},
                )
                pipeline_warnings.append(
                    f"summary_generation: LLM summary failed, using template — {str(sum_exc)[:200]}"
                )

        summary_row = repo.upsert_summary(
            room_id=room_id,
            run_id=run_id,
            summary_type="diligence_overview",
            status="ready",
            content_markdown=summary_payload["markdown"],
            citations=summary_payload["citations"],
            confidence=summary_payload["confidence"],
            metadata={"engine": summary_engine, **summary_payload.get("metadata", {})},
            actor_user_id=user_id,
        )

        evidence_spans = []
        for entry, item_row in zip(checklist_entries, checklist_rows):
            for evidence in normalize_evidence_records(entry.get("evidence", [])):
                evidence_spans.append({**evidence, "entity_type": "checklist_item", "entity_id": item_row.id})
        for entry, finding_row in zip(verified_finding_entries, finding_rows):
            for evidence in normalize_evidence_records(entry.get("evidence_list", [])):
                evidence_spans.append({**evidence, "entity_type": "finding", "entity_id": finding_row.id})
        for evidence in normalize_evidence_records(summary_payload.get("evidence_list", [])):
            evidence_spans.append({**evidence, "entity_type": "summary", "entity_id": summary_row.id})
        repo.replace_evidence_spans(room_id=room_id, run_id=run_id, spans=evidence_spans)

        repo.update_analysis_run(
            run_id=run_id,
            status="completed",
            current_stage="completed",
            progress_percent=100,
            completed_at=datetime.utcnow(),
            metadata_patch={
                "verification": verification_stats,
                "document_classification_summary": classification_summary,
                "pipeline_warnings": pipeline_warnings if pipeline_warnings else None,
            },
        )
        repo.mark_room_status(room_id=room_id, status="completed", last_analyzed_at=datetime.utcnow())
        repo.add_audit_event(
            room_id=room_id,
            analysis_run_id=run_id,
            actor_user_id=user_id,
            event_type="analysis.completed",
            entity_type="analysis_run",
            entity_id=run_id,
            payload={
                "checklist_items": len(checklist_rows),
                "findings": len(finding_rows),
                "evidence_spans": len(evidence_spans),
                "clause_hits": len(clause_hits),
                "numeric_signals": {metric: len(rows) for metric, rows in numeric_signals.items()},
                "verification": verification_stats,
                "document_classification": {doc_id: value.get("document_type") for doc_id, value in document_classifications.items()},
            },
        )
        if not finding_rows and not checklist_rows:
            pipeline_warnings.append(
                "No findings or checklist items were produced — all pipeline stages may have failed. "
                "Check worker logs for errors in clause extraction and per-doc analysis."
            )
        if tracker:
            tracker.mark_completed()
        return {"status": "completed", "analysis_run_id": run_id}

    except PipelineCriticalError as exc:
        logger.error(
            f"PE diligence pipeline stopped at critical stage '{exc.stage}': {exc}",
            extra={"room_id": room_id, "run_id": run_id, "stage": exc.stage},
        )
        repo.update_analysis_run(
            run_id=run_id,
            status="failed",
            current_stage=exc.stage,
            progress_percent=100,
            error_message=str(exc)[:1000],
            completed_at=datetime.utcnow(),
        )
        if tracker:
            tracker.mark_error(error_message="Analysis failed — please try again.", internal_error=str(exc)[:1000], error_stage=exc.stage, is_retryable=False)
        repo.mark_room_status(room_id=room_id, status="failed")
        repo.add_audit_event(
            room_id=room_id,
            analysis_run_id=run_id,
            actor_user_id=user_id,
            event_type="analysis.failed",
            entity_type="analysis_run",
            entity_id=run_id,
            payload={"error": str(exc)[:1000], "stage": exc.stage},
        )
        return {"status": "failed", "analysis_run_id": run_id, "error": str(exc), "stage": exc.stage}

    except Exception as exc:
        logger.exception("PE diligence analysis task failed", extra={"room_id": room_id, "run_id": run_id})
        repo.update_analysis_run(
            run_id=run_id,
            status="failed",
            current_stage="failed",
            progress_percent=100,
            error_message=str(exc)[:1000],
            completed_at=datetime.utcnow(),
        )
        if tracker:
            tracker.mark_error(error_message="Analysis failed — please try again.", internal_error=str(exc)[:1000], error_stage="analysis", is_retryable=False)
        repo.mark_room_status(room_id=room_id, status="failed")
        repo.add_audit_event(
            room_id=room_id,
            analysis_run_id=run_id,
            actor_user_id=user_id,
            event_type="analysis.failed",
            entity_type="analysis_run",
            entity_id=run_id,
            payload={"error": str(exc)[:1000]},
        )
        return {"status": "failed", "analysis_run_id": run_id, "error": str(exc)}
    finally:
        db.close()


@shared_task(bind=True)
def cleanup_stale_analysis_runs(self) -> Dict[str, Any]:
    """Mark stale running analysis runs as failed and close any open SSE streams."""
    from app.db_models import JobState
    from app.services.pubsub import publish_event

    stale_cutoff_minutes = 30
    db = SessionLocal()
    try:
        repo = PEDiligenceRepository(db)
        stale_runs = repo.get_stale_running_analysis_runs(older_than_minutes=stale_cutoff_minutes)
        if not stale_runs:
            return {"cleaned": 0}

        cleaned = 0
        for run in stale_runs:
            try:
                repo.update_analysis_run(
                    run_id=run.id,
                    status="failed",
                    current_stage="failed",
                    progress_percent=100,
                    error_message=f"Analysis timed out after {stale_cutoff_minutes} minutes. The worker may have crashed.",
                    completed_at=datetime.utcnow(),
                )

                job_state = db.query(JobState).filter(JobState.job_id == run.job_id).first()
                if job_state:
                    job_state.status = "failed"
                    job_state.error_message = f"Worker timed out after {stale_cutoff_minutes} minutes"
                    db.commit()

                if run.job_id:
                    try:
                        publish_event(
                            run.job_id,
                            "error",
                            {
                                "error_stage": "analysis",
                                "error_message": "Analysis timed out. Please re-run.",
                                "is_retryable": True,
                            },
                        )
                        publish_event(run.job_id, "end", {"reason": "failed"})
                    except Exception:
                        pass

                logger.warning(
                    "Cleaned up stale analysis run",
                    extra={"run_id": run.id, "room_id": run.room_id, "job_id": run.job_id},
                )
                cleaned += 1
            except Exception as run_exc:
                logger.error(f"Failed to clean up stale run {run.id}: {run_exc}", extra={"run_id": run.id})

        return {"cleaned": cleaned}
    finally:
        db.close()
