"""Private Equity Diligence Investigation API."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from app.auth import _claim, _verify_token, get_current_user
from app.database import SessionLocal, get_db
from app.services.pubsub import safe_subscribe
from app.utils.logging import logger
from app.db_models_users import User
from app.verticals.private_equity.diligence.investigations.schemas import (
    CreateInvestigationRequest,
    CreateInvestigationResponse,
    EvidenceSearchRequest,
    EvidenceSearchResponse,
    InvestigationClaimOut,
    InvestigationDetailOut,
    InvestigationOut,
    InvestigationRunOut,
    OverrideClaimRequest,
    RerunInvestigationResponse,
)
from app.verticals.private_equity.diligence.investigations.service import (
    PEDiligenceInvestigationService,
)
from app.verticals.private_equity.diligence.schemas import EvidenceSpanOut


router = APIRouter(prefix="/diligence", tags=["pe_diligence_investigations"])


def _run_out(run) -> InvestigationRunOut:
    return InvestigationRunOut.model_validate(
        {
            **run.__dict__,
            "metadata": run.metadata_json if isinstance(run.metadata_json, dict) else {},
        }
    )


def _investigation_out(investigation, latest_run=None) -> InvestigationOut:
    return InvestigationOut.model_validate(
        {
            **investigation.__dict__,
            "metadata": investigation.metadata_json if isinstance(investigation.metadata_json, dict) else {},
            "latest_run": _run_out(latest_run) if latest_run else None,
        }
    )


def _span_out(span) -> EvidenceSpanOut:
    return EvidenceSpanOut.model_validate(
        {
            **span.__dict__,
            "metadata": span.metadata_json if isinstance(span.metadata_json, dict) else {},
        }
    )


@router.post("/rooms/{room_id}/investigations", response_model=CreateInvestigationResponse)
def create_investigation(
    room_id: str,
    payload: CreateInvestigationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = PEDiligenceInvestigationService(db)
    try:
        investigation, run, reused_running_run = service.create_investigation(
            room_id=room_id,
            org_id=user.org_id,
            user_id=user.id,
            investigation_type=payload.investigation_type,
            title=payload.title,
            question=payload.question,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return CreateInvestigationResponse(
        investigation=_investigation_out(investigation, latest_run=run),
        run=_run_out(run),
        reused_running_run=reused_running_run,
    )


@router.get("/rooms/{room_id}/investigations", response_model=List[InvestigationOut])
def list_investigations(
    room_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = PEDiligenceInvestigationService(db)
    try:
        investigations = service.list_investigations(
            room_id=room_id,
            org_id=user.org_id,
            user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return [
        _investigation_out(
            investigation,
            latest_run=service.repo.get_latest_run(investigation_id=investigation.id),
        )
        for investigation in investigations
    ]


@router.get("/rooms/{room_id}/investigations/{investigation_id}", response_model=InvestigationDetailOut)
def get_investigation_detail(
    room_id: str,
    investigation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = PEDiligenceInvestigationService(db)
    try:
        investigation, claims, claim_spans, latest_run, conclusion_spans = service.get_investigation_detail(
            room_id=room_id,
            investigation_id=investigation_id,
            org_id=user.org_id,
            user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    spans_by_claim = defaultdict(list)
    for span in claim_spans:
        spans_by_claim[span.entity_id].append(_span_out(span))

    claim_out = [
        InvestigationClaimOut.model_validate(
            {
                **claim.__dict__,
                "metadata": claim.metadata_json if isinstance(claim.metadata_json, dict) else {},
                "reason_codes": [
                    str(code)
                    for code in ((claim.metadata_json or {}).get("decision_reason_codes") or [])
                    if code is not None
                ],
                "evidence_spans": spans_by_claim.get(claim.id, []),
            }
        )
        for claim in claims
    ]

    return InvestigationDetailOut.model_validate(
        {
            **investigation.__dict__,
            "metadata": investigation.metadata_json if isinstance(investigation.metadata_json, dict) else {},
            "latest_run": _run_out(latest_run) if latest_run else None,
            "claims": claim_out,
            "conclusion_evidence_spans": [_span_out(span) for span in conclusion_spans],
        }
    )


@router.post(
    "/rooms/{room_id}/investigations/{investigation_id}/rerun",
    response_model=RerunInvestigationResponse,
)
def rerun_investigation(
    room_id: str,
    investigation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = PEDiligenceInvestigationService(db)
    try:
        investigation, run, reused_running_run = service.rerun_investigation(
            room_id=room_id,
            investigation_id=investigation_id,
            org_id=user.org_id,
            user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return RerunInvestigationResponse(
        investigation=_investigation_out(investigation, latest_run=run),
        run=_run_out(run),
        reused_running_run=reused_running_run,
    )


@router.patch(
    "/rooms/{room_id}/investigations/{investigation_id}/claims/{claim_id}/verification",
    response_model=InvestigationClaimOut,
)
def override_claim_verification(
    room_id: str,
    investigation_id: str,
    claim_id: str,
    payload: OverrideClaimRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = PEDiligenceInvestigationService(db)
    try:
        claim = service.override_claim(
            room_id=room_id,
            investigation_id=investigation_id,
            claim_id=claim_id,
            verification_status=payload.verification_status,
            override_reason=payload.override_reason,
            reviewer_notes=payload.reviewer_notes,
            actor_user_id=user.id,
            org_id=user.org_id,
            user_id=user.id,
        )
    except ValueError as exc:
        msg = str(exc)
        if "archived" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=404, detail=msg)

    service.repo.add_audit_event(
        room_id=room_id,
        actor_user_id=user.id,
        event_type="investigation_claim.overridden",
        entity_type="investigation_claim",
        entity_id=claim_id,
        payload={
            "new_status": payload.verification_status,
            "reason": payload.override_reason,
        },
    )

    try:
        from app.utils.metrics import INVESTIGATION_CLAIM_OVERRIDES_TOTAL
        _inv = service.repo.get_investigation(
            investigation_id=investigation_id,
            room_id=room_id,
            org_id=user.org_id,
            user_id=user.id,
        )
        INVESTIGATION_CLAIM_OVERRIDES_TOTAL.labels(
            investigation_type=_inv.investigation_type if _inv else "unknown",
            new_status=payload.verification_status,
        ).inc()
    except Exception:
        pass

    spans = service.repo.get_evidence_for_entities(
        room_id=room_id,
        entity_type="investigation_claim",
        entity_ids=[claim.id],
    )
    return InvestigationClaimOut.model_validate(
        {
            **claim.__dict__,
            "metadata": claim.metadata_json if isinstance(claim.metadata_json, dict) else {},
            "reason_codes": [
                str(code)
                for code in ((claim.metadata_json or {}).get("decision_reason_codes") or [])
                if code is not None
            ],
            "evidence_spans": [_span_out(s) for s in spans],
        }
    )


@router.get(
    "/rooms/{room_id}/investigations/{investigation_id}/runs/{run_id}/stream",
)
async def stream_investigation_run(
    room_id: str,
    investigation_id: str,
    run_id: str,
    token: Optional[str] = Query(None),
):
    """SSE endpoint for real-time investigation run progress.

    Auth is via ?token= query param because EventSource cannot set custom headers.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    try:
        token_payload = _verify_token(token)
        user_id = token_payload.get("sub")
        org_id = token_payload.get(_claim("org_id"))
        if not user_id or not org_id:
            raise HTTPException(status_code=401, detail="Invalid token claims")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    # Ownership check — short-lived session, closed before streaming starts.
    db = SessionLocal()
    try:
        from app.verticals.private_equity.diligence.investigations.repository import (
            PEDiligenceInvestigationRepository,
        )
        repo = PEDiligenceInvestigationRepository(db)
        investigation = repo.get_investigation(
            investigation_id=investigation_id,
            room_id=room_id,
            org_id=org_id,
            user_id=user_id,
        )
        if not investigation:
            raise HTTPException(status_code=404, detail="Investigation not found")

        run = repo.get_run(run_id=run_id, investigation_id=investigation_id)
        if not run:
            raise HTTPException(status_code=404, detail="Investigation run not found")

        initial_state = {
            "status": run.status,
            "current_stage": run.current_stage,
            "progress_percent": run.progress_percent,
            "error_message": run.error_message,
        }
    finally:
        db.close()

    async def event_generator():
        end_sent = False
        status = initial_state["status"]

        # Already-terminal runs: send snapshot and close immediately.
        if status == "completed":
            yield ServerSentEvent(
                data=json.dumps({
                    "stage": "completed",
                    "progress_percent": 100,
                    "investigation_id": investigation_id,
                    "status": "completed",
                }),
                event="complete",
            )
            yield ServerSentEvent(
                data=json.dumps({"reason": "completed", "run_id": run_id}),
                event="end",
            )
            return

        if status == "failed":
            yield ServerSentEvent(
                data=json.dumps({
                    "stage": "failed",
                    "message": initial_state["error_message"] or "Investigation failed",
                }),
                event="error",
            )
            yield ServerSentEvent(
                data=json.dumps({"reason": "failed", "run_id": run_id}),
                event="end",
            )
            return

        # In-progress: send current snapshot then stream pub/sub.
        yield ServerSentEvent(
            data=json.dumps({
                "stage": initial_state["current_stage"],
                "progress_percent": initial_state["progress_percent"],
                "status": status,
            }),
            event="progress",
        )

        pubsub = safe_subscribe(f"investigation:{run_id}")
        max_duration = 800
        elapsed = 0
        keepalive_interval = 8
        last_keepalive = 0

        try:
            while elapsed < max_duration:
                message = pubsub.get_message(timeout=1.0)
                if message and message.get("type") == "message":
                    try:
                        data = json.loads(message["data"])
                        event_type = data.get("event")
                        evt_payload = data.get("payload", {})
                        if event_type:
                            yield ServerSentEvent(data=json.dumps(evt_payload), event=event_type)
                            if event_type in ("complete", "error"):
                                yield ServerSentEvent(
                                    data=json.dumps({"reason": event_type, "run_id": run_id}),
                                    event="end",
                                )
                                end_sent = True
                                break
                            elif event_type == "end":
                                end_sent = True
                                break
                    except Exception as e:
                        logger.warning(
                            "Malformed investigation pubsub message",
                            extra={"run_id": run_id, "error": str(e)},
                        )
                else:
                    if (elapsed - last_keepalive) >= keepalive_interval:
                        yield ": keepalive\n\n"
                        last_keepalive = elapsed

                await asyncio.sleep(1)
                elapsed += 1

            if not end_sent:
                if elapsed >= max_duration:
                    yield ServerSentEvent(
                        data=json.dumps({"message": "Stream timeout", "type": "timeout"}),
                        event="error",
                    )
                yield ServerSentEvent(
                    data=json.dumps({
                        "reason": "timeout" if elapsed >= max_duration else "normal",
                        "run_id": run_id,
                    }),
                    event="end",
                )
        except Exception as e:
            logger.exception(
                "SSE stream error for investigation run",
                extra={"run_id": run_id, "error": str(e)},
            )
            if not end_sent:
                yield ServerSentEvent(
                    data=json.dumps({"message": "Stream error", "type": "stream_error"}),
                    event="error",
                )
                yield ServerSentEvent(
                    data=json.dumps({"reason": "stream_error", "run_id": run_id}),
                    event="end",
                )
        finally:
            try:
                pubsub.close()
            except Exception:
                pass

    return EventSourceResponse(
        event_generator(),
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Content-Type": "text/event-stream; charset=utf-8",
        },
    )


@router.post("/rooms/{room_id}/evidence/search", response_model=EvidenceSearchResponse)
def search_evidence(
    room_id: str,
    payload: EvidenceSearchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = PEDiligenceInvestigationService(db)
    try:
        rows = service.search_evidence(
            room_id=room_id,
            org_id=user.org_id,
            user_id=user.id,
            query=payload.query,
            document_ids=payload.document_ids,
            top_k=payload.top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return EvidenceSearchResponse(
        query=payload.query,
        top_k=payload.top_k,
        results=rows,
    )
