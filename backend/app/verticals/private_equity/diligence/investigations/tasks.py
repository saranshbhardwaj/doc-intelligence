"""Celery tasks for PE diligence investigations."""
from __future__ import annotations

import asyncio
from datetime import datetime
from statistics import mean
from typing import Any, Dict, List, Set

from celery import shared_task

from app.config import settings
from app.database import SessionLocal
from app.repositories.document_repository import DocumentRepository
from app.utils.logging import logger
from app.verticals.private_equity.diligence.investigations.claim_builder import (
    SIGNAL_REGISTRY,
    build_change_of_control_claims,
)
from app.verticals.private_equity.diligence.investigations.coverage import (
    compute_coverage_metrics,
    should_expand_search,
)
from app.verticals.private_equity.diligence.investigations.llm_claim_builder import (
    LLMClaimBuilder,
    merge_llm_claims_into,
)
from app.verticals.private_equity.diligence.investigations.repository import PEDiligenceInvestigationRepository
from app.verticals.private_equity.diligence.investigations.retriever import (
    route_candidate_documents,
    search_evidence_chunks,
    to_evidence_search_rows,
)
from app.verticals.private_equity.diligence.investigations.templates import get_template
from app.verticals.private_equity.diligence.service import PEDiligenceService


def _publish_run_progress(run_id: str, event: str, payload: dict) -> None:
    """Publish investigation run progress to Redis pub/sub. Never raises."""
    try:
        from app.services.pubsub import publish_event
        publish_event(f"investigation:{run_id}", event, payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to publish investigation progress",
            extra={"run_id": run_id, "error": str(exc)[:200]},
        )


def _emit_run_metrics(investigation_type: str, final_status: str, claims: List[dict], coverage: Dict[str, Any]) -> None:
    """Emit Prometheus metrics for a completed investigation run. Never raises."""
    try:
        from app.utils.metrics import (
            INVESTIGATION_CLAIMS_TOTAL,
            INVESTIGATION_COVERAGE_SCORE,
            INVESTIGATION_RUNS_TOTAL,
        )
        INVESTIGATION_RUNS_TOTAL.labels(
            investigation_type=investigation_type,
            status=final_status,
        ).inc()
        for claim in claims:
            INVESTIGATION_CLAIMS_TOTAL.labels(
                investigation_type=investigation_type,
                stance=claim.get("stance") or "unknown",
                verification_status=claim.get("verification_status") or "needs_review",
            ).inc()
        coverage_score = float(coverage.get("coverage_score", 0.0))
        coverage_status = str(coverage.get("coverage_status", "weak"))
        INVESTIGATION_COVERAGE_SCORE.labels(
            investigation_type=investigation_type,
            coverage_status=coverage_status,
        ).observe(coverage_score)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to emit investigation run metrics",
            extra={"investigation_type": investigation_type, "error": str(exc)[:200]},
        )


def _emit_run_failed_metric(investigation_type: str) -> None:
    """Emit failed run counter. Never raises."""
    try:
        from app.utils.metrics import INVESTIGATION_RUNS_TOTAL
        INVESTIGATION_RUNS_TOTAL.labels(investigation_type=investigation_type, status="failed").inc()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to emit investigation failed metric",
            extra={"investigation_type": investigation_type, "error": str(exc)[:200]},
        )


def _build_conclusion(investigation_title: str, claims: List[dict], coverage: Dict[str, Any]) -> str:
    supported = [c for c in claims if c.get("stance") == "supported"]
    contradicted = [c for c in claims if c.get("stance") == "contradicted"]
    needs_review = [c for c in claims if c.get("verification_status") == "needs_review"]
    lines = [
        f"# {investigation_title}",
        "",
        f"- Coverage status: **{coverage.get('coverage_status', 'unknown')}** ({coverage.get('coverage_score', 0.0)})",
        f"- Documents reviewed: **{coverage.get('documents_targeted', 0)}** targeted / **{coverage.get('documents_total', 0)}** total",
        f"- Evidence spans: **{coverage.get('evidence_span_count', 0)}**",
        "",
        "## Outcome",
    ]
    if supported:
        lines.append(f"- Supported claims: **{len(supported)}**")
    if contradicted:
        lines.append(f"- Contradicted claims: **{len(contradicted)}**")
    if needs_review:
        lines.append(f"- Needs review claims: **{len(needs_review)}**")
    lines.extend(["", "## Claim Summary"])
    for claim in claims:
        lines.append(
            f"- **{claim.get('claim_text')}** -> `{claim.get('stance')}` "
            f"(verification: `{claim.get('verification_status')}`, confidence: {claim.get('confidence')})"
        )
    return "\n".join(lines)


@shared_task(bind=True)
def run_diligence_investigation_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    room_id = payload["room_id"]
    investigation_id = payload["investigation_id"]
    run_id = payload["run_id"]
    org_id = payload["org_id"]
    user_id = payload["user_id"]

    db = SessionLocal()
    repo = PEDiligenceInvestigationRepository(db)
    doc_repo = DocumentRepository()
    investigation_type_str: str = "unknown"  # set once investigation is loaded

    try:
        repo.update_run(
            run_id=run_id,
            status="running",
            current_stage="load_context",
            progress_percent=5,
            started_at=datetime.utcnow(),
        )
        _publish_run_progress(run_id, "progress", {"stage": "load_context", "progress_percent": 5, "status": "running"})
        repo.update_investigation(investigation_id=investigation_id, status="running")

        investigation = repo.get_investigation(
            investigation_id=investigation_id,
            room_id=room_id,
            org_id=org_id,
            user_id=user_id,
        )
        if not investigation:
            raise ValueError("Investigation not found")

        investigation_type_str = investigation.investigation_type
        template = get_template(investigation.investigation_type)
        room_docs = repo.list_room_documents(room_id=room_id)
        all_doc_ids = [row.document_id for row in room_docs if row.document_id]
        if not all_doc_ids:
            raise ValueError("No documents attached to room for investigation")

        repo.update_run(
            run_id=run_id,
            current_stage="soft_prereq_check",
            progress_percent=12,
        )
        _publish_run_progress(run_id, "progress", {"stage": "soft_prereq_check", "progress_percent": 12, "status": "running"})
        analysis_status = "completed"
        latest_analysis = repo.get_latest_completed_analysis_run(room_id=room_id)
        if not latest_analysis:
            analysis_status = "missing"
            active_analysis = repo.get_active_analysis_run(room_id=room_id)
            if not active_analysis:
                # Soft prereq: trigger analysis in background, continue with provisional investigation.
                PEDiligenceService(db).start_analysis(
                    room_id=room_id,
                    org_id=org_id,
                    user_id=user_id,
                    force_reanalyze=False,
                )
                analysis_status = "triggered"

        doc_info_rows = doc_repo.get_doc_info_by_ids(all_doc_ids)
        doc_info_by_id = {row["id"]: row for row in doc_info_rows}

        room_doc_dicts = []
        doc_classifications: Dict[str, dict] = {}
        contract_families: Dict[str, List[dict]] = {}
        for row in room_docs:
            meta = row.metadata_json or {}
            room_doc_dicts.append(
                {
                    "document_id": row.document_id,
                    "metadata_json": meta,
                }
            )
            # Extract classification if present (from analysis run).
            classification = meta.get("document_classification")
            if isinstance(classification, dict) and row.document_id:
                doc_classifications[row.document_id] = classification
            # Build contract family map from amendment linking (T11).
            link = meta.get("amendment_link")
            if link and link.get("parent_document_id") and row.document_id:
                parent_id = link["parent_document_id"]
                contract_families.setdefault(parent_id, []).append({
                    "amendment_doc_id": row.document_id,
                    "amendment_type": link.get("amendment_type"),
                    "confidence": float(link.get("confidence") or 0.0),
                })

        repo.update_run(
            run_id=run_id,
            current_stage="route_candidates",
            progress_percent=18,
        )
        _publish_run_progress(run_id, "progress", {"stage": "route_candidates", "progress_percent": 18, "status": "running"})
        candidate_doc_ids = route_candidate_documents(
            room_documents=room_doc_dicts,
            doc_info_by_id=doc_info_by_id,
            doc_type_hints=template.get("document_type_hints", []),
            filename_hints=template.get("filename_hints", []),
        )
        if not candidate_doc_ids:
            candidate_doc_ids = list(all_doc_ids)

        repo.update_run(
            run_id=run_id,
            current_stage="retrieve_targeted",
            progress_percent=34,
        )
        _publish_run_progress(run_id, "progress", {"stage": "retrieve_targeted", "progress_percent": 34, "status": "running"})
        seed_queries = list(template.get("seed_queries", []))
        if investigation.question:
            seed_queries.insert(0, investigation.question)
        targeted_chunks = search_evidence_chunks(
            db=db,
            queries=seed_queries,
            document_ids=candidate_doc_ids,
            top_k_per_query=20,
            max_results=30,
        )
        targeted_evidence_rows = to_evidence_search_rows(targeted_chunks, top_k=len(targeted_chunks))
        coverage = compute_coverage_metrics(
            total_documents=len(all_doc_ids),
            targeted_documents=len(candidate_doc_ids),
            scanned_chunks=len(targeted_chunks),
            evidence_rows=targeted_evidence_rows,
            retrieval_mode="targeted_only",
            document_classifications=doc_classifications or None,
        )

        retrieval_mode = "targeted_only"
        final_chunks = targeted_chunks
        final_evidence_rows = targeted_evidence_rows

        repo.update_run(
            run_id=run_id,
            current_stage="coverage_gate",
            progress_percent=52,
        )
        _publish_run_progress(run_id, "progress", {"stage": "coverage_gate", "progress_percent": 52, "status": "running"})
        if should_expand_search(coverage):
            expanded_chunks = search_evidence_chunks(
                db=db,
                queries=seed_queries,
                document_ids=all_doc_ids,
                top_k_per_query=25,
                max_results=55,
            )
            expanded_evidence_rows = to_evidence_search_rows(expanded_chunks, top_k=len(expanded_chunks))
            expanded_coverage = compute_coverage_metrics(
                total_documents=len(all_doc_ids),
                targeted_documents=len(all_doc_ids),
                scanned_chunks=len(expanded_chunks),
                evidence_rows=expanded_evidence_rows,
                retrieval_mode="expanded_all_docs",
                document_classifications=doc_classifications or None,
            )
            if expanded_coverage.get("coverage_score", 0.0) >= coverage.get("coverage_score", 0.0):
                final_chunks = expanded_chunks
                final_evidence_rows = expanded_evidence_rows
                coverage = expanded_coverage
                retrieval_mode = "expanded_all_docs"

        repo.update_run(
            run_id=run_id,
            current_stage="build_claims",
            progress_percent=65,
        )
        _publish_run_progress(run_id, "progress", {"stage": "build_claims", "progress_percent": 65, "status": "running"})
        claims, claim_evidence_map = build_change_of_control_claims(final_chunks, coverage)

        # --- LLM claim augmentation (optional) ---
        # Identify chunks that produced no regex hits and send to LLM
        # for paraphrased/unusual clause detection.
        llm_rejected: List[dict] = []
        if settings.pe_diligence_investigation_llm_enabled:
            repo.update_run(
                run_id=run_id,
                current_stage="llm_claim_augmentation",
                progress_percent=72,
            )
            _publish_run_progress(run_id, "progress", {"stage": "llm_claim_augmentation", "progress_percent": 72, "status": "running"})
            matched_chunk_ids: Set[str] = set()
            for chunk in final_chunks:
                text = str(chunk.get("text") or "")
                if not text:
                    continue
                for entry in SIGNAL_REGISTRY:
                    if entry.pattern.search(text):
                        matched_chunk_ids.add(str(chunk.get("id") or ""))
                        break

            unmatched_chunks = [
                c for c in final_chunks
                if str(c.get("id") or "") not in matched_chunk_ids
                and c.get("text")
            ][:settings.pe_diligence_investigation_llm_max_chunks]

            if unmatched_chunks:
                try:
                    builder = LLMClaimBuilder()
                    llm_claims, llm_rejected = asyncio.run(
                        builder.augment_claims(
                            chunks=unmatched_chunks,
                            investigation_type=investigation.investigation_type,
                            investigation_title=investigation.title,
                            investigation_question=investigation.question or "",
                        )
                    )
                    if llm_claims:
                        claims, claim_evidence_map = merge_llm_claims_into(
                            regex_claims=claims,
                            regex_evidence=claim_evidence_map,
                            llm_claims=llm_claims,
                        )
                except Exception as llm_exc:
                    logger.warning(
                        "LLM claim augmentation failed; continuing with regex-only claims",
                        extra={
                            "investigation_id": investigation_id,
                            "run_id": run_id,
                            "error": str(llm_exc)[:500],
                        },
                    )

            # Audit rejected LLM claims
            for rejected in llm_rejected:
                repo.add_audit_event(
                    room_id=room_id,
                    actor_user_id=user_id,
                    event_type="investigation.llm_claim_rejected",
                    entity_type="investigation",
                    entity_id=investigation_id,
                    payload={
                        "run_id": run_id,
                        "reason": rejected.get("reason"),
                        "claim_key": rejected.get("claim_key"),
                        "chunk_id": rejected.get("chunk_id"),
                    },
                )

        repo.update_run(
            run_id=run_id,
            current_stage="reconcile_amendments",
            progress_percent=75,
        )
        _publish_run_progress(run_id, "progress", {"stage": "reconcile_amendments", "progress_percent": 75, "status": "running"})
        if contract_families:
            from app.verticals.private_equity.diligence.investigations.reconciler import reconcile_amendment_claims
            claims = reconcile_amendment_claims(
                claims=claims,
                claim_evidence_map=claim_evidence_map,
                contract_families=contract_families,
            )

        repo.update_run(
            run_id=run_id,
            current_stage="score_gate",
            progress_percent=78,
        )
        _publish_run_progress(run_id, "progress", {"stage": "score_gate", "progress_percent": 78, "status": "running"})
        coverage_score_value = float(coverage.get("coverage_score", 0.0))
        for claim in claims:
            interpretation_confidence = claim.get("interpretation_confidence")
            if interpretation_confidence is None:
                interpretation_confidence = float(claim.get("confidence") or 0.0)

            metadata_json = dict(claim.get("metadata_json") or {})
            reason_codes = [str(code) for code in (metadata_json.get("decision_reason_codes") or [])]
            if float(interpretation_confidence) >= 0.8 and coverage_score_value < 0.5:
                if "low_coverage_high_confidence" not in reason_codes:
                    reason_codes.append("low_coverage_high_confidence")
                claim["verification_status"] = "needs_review"
            if float(interpretation_confidence) < 0.6 and coverage_score_value >= 0.7:
                if "low_confidence_high_coverage" not in reason_codes:
                    reason_codes.append("low_confidence_high_coverage")
                claim["verification_status"] = "needs_review"

            if claim.get("verification_status") == "needs_review" and not reason_codes:
                reason_codes.append("insufficient_evidence")

            metadata_json["decision_reason_codes"] = reason_codes
            claim["metadata_json"] = metadata_json
            claim.setdefault("status", "proposed")
            claim.setdefault("supersedes_claim_id", None)
            claim["interpretation_confidence"] = float(interpretation_confidence)
            claim["coverage_score"] = coverage_score_value
            claim.setdefault("source_workers", ["rule"])
            claim.setdefault("confidence_history", [float(interpretation_confidence)])
        claim_rows = repo.replace_claims(
            investigation_id=investigation_id,
            run_id=run_id,
            room_id=room_id,
            claims=claims,
        )

        repo.update_run(
            run_id=run_id,
            current_stage="persist_evidence",
            progress_percent=84,
        )
        _publish_run_progress(run_id, "progress", {"stage": "persist_evidence", "progress_percent": 84, "status": "running"})
        claim_id_by_key = {row.claim_key: row.id for row in claim_rows}
        old_entity_ids = [row.id for row in claim_rows] + [investigation_id]
        repo.delete_investigation_evidence(room_id=room_id, entity_ids=old_entity_ids)

        spans_to_create: List[dict] = []
        for claim_key, claim_id in claim_id_by_key.items():
            for evidence in claim_evidence_map.get(claim_key, []):
                spans_to_create.append(
                    {
                        **evidence,
                        "entity_type": "investigation_claim",
                        "entity_id": claim_id,
                    }
                )

        for row in final_evidence_rows[:4]:
            spans_to_create.append(
                {
                    "entity_type": "investigation_conclusion",
                    "entity_id": investigation_id,
                    "source_document_id": row.get("document_id"),
                    "source_chunk_id": row.get("chunk_id"),
                    "source_page_number": row.get("page_number"),
                    "char_start": None,
                    "char_end": None,
                    "quote": row.get("quote"),
                    "confidence": row.get("hybrid_score"),
                    "metadata_json": {
                        "bbox": row.get("bbox"),
                        "source_page_range": row.get("page_range") or [],
                        "hybrid_score": row.get("hybrid_score"),
                    },
                }
            )

        if spans_to_create:
            repo.create_evidence_spans(room_id=room_id, spans=spans_to_create)

        avg_conf = mean([float(c.get("confidence") or 0.0) for c in claims]) if claims else 0.0
        coverage_status = str(coverage.get("coverage_status", "weak"))
        needs_review = any(c.get("verification_status") == "needs_review" for c in claims) or coverage_status == "weak"
        final_status = "needs_review" if needs_review else "completed"
        conclusion = _build_conclusion(investigation.title, claims, coverage)

        repo.update_run(
            run_id=run_id,
            status="completed",
            current_stage="completed",
            progress_percent=100,
            completed_at=datetime.utcnow(),
            metadata_patch={
                "coverage": coverage,
                "retrieval_mode": retrieval_mode,
                "analysis_soft_prereq_status": analysis_status,
            },
        )
        repo.update_investigation(
            investigation_id=investigation_id,
            status=final_status,
            conclusion_markdown=conclusion,
            confidence=round(avg_conf, 3),
            coverage_score=float(coverage.get("coverage_score", 0.0)),
            coverage_status=coverage_status,
            metadata_patch={
                "coverage": coverage,
                "retrieval_mode": retrieval_mode,
                "analysis_soft_prereq_status": analysis_status,
            },
            completed_at=datetime.utcnow(),
        )
        repo.add_audit_event(
            room_id=room_id,
            actor_user_id=user_id,
            event_type="investigation.completed",
            entity_type="investigation",
            entity_id=investigation_id,
            payload={
                "run_id": run_id,
                "investigation_type": investigation.investigation_type,
                "status": final_status,
                "coverage": coverage,
                "analysis_soft_prereq_status": analysis_status,
            },
        )
        _publish_run_progress(run_id, "complete", {
            "stage": "completed",
            "progress_percent": 100,
            "investigation_id": investigation_id,
            "status": final_status,
        })
        _publish_run_progress(run_id, "end", {"reason": "completed", "run_id": run_id})
        _emit_run_metrics(investigation.investigation_type, final_status, claims, coverage)
        return {"status": "completed", "investigation_id": investigation_id, "run_id": run_id}
    except Exception as exc:
        logger.exception(
            "PE diligence investigation task failed",
            extra={"room_id": room_id, "investigation_id": investigation_id, "run_id": run_id},
        )
        repo.update_run(
            run_id=run_id,
            status="failed",
            current_stage="failed",
            progress_percent=100,
            error_message=str(exc)[:1000],
            completed_at=datetime.utcnow(),
        )
        repo.update_investigation(
            investigation_id=investigation_id,
            status="failed",
            metadata_patch={"last_error": str(exc)[:1000]},
            completed_at=datetime.utcnow(),
        )
        repo.add_audit_event(
            room_id=room_id,
            actor_user_id=user_id,
            event_type="investigation.failed",
            entity_type="investigation",
            entity_id=investigation_id,
            payload={"run_id": run_id, "error": str(exc)[:1000]},
        )
        _publish_run_progress(run_id, "error", {"stage": "failed", "message": str(exc)[:500]})
        _publish_run_progress(run_id, "end", {"reason": "failed", "run_id": run_id})
        _emit_run_failed_metric(investigation_type_str)
        return {
            "status": "failed",
            "investigation_id": investigation_id,
            "run_id": run_id,
            "error": str(exc),
        }
    finally:
        db.close()

