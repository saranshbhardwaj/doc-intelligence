from fastapi import APIRouter, Depends, HTTPException, Response, Query
from app.repositories.workflow_repository import WorkflowRepository
from app.database import get_db
from app.schemas.workflows import ExportRequest
from app.services.exporter import export_bytes
from app.services.artifacts import load_artifact
from app.utils.metrics import (
    EXPORT_GENERATION_SECONDS,
    EXPORT_R2_STORE_SECONDS,
    EXPORT_R2_FAILURES,
    EXPORT_REQUESTS,
    EXPORT_BYTES_TOTAL,
)
from app.utils.logging import logger
from app.config import settings
from app.services.storage.cloudflare_r2 import get_r2_storage
import json

router = APIRouter(prefix='/export', tags=['export'])


@router.post('/generate')
def generate_export(
    req: ExportRequest,
    delivery: str = Query("stream", description="stream | url (return signed URL if Cloudflare R2 enabled)"),
    db=Depends(get_db)
):
    repo = WorkflowRepository(next(db))
    run = repo.get_run(req.run_id)
    if not run:
        raise HTTPException(status_code=404, detail='run not found')
    if not run.artifact:
        raise HTTPException(status_code=400, detail='no artifact available')
    raw = run.artifact
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        logger.exception('Invalid artifact stored')
        raise HTTPException(status_code=500, detail='invalid artifact stored')

    # If artifact is a pointer, load from storage
    full_artifact = load_artifact(parsed)
    obj = full_artifact.get('parsed') or full_artifact.get('partial_parsed') or full_artifact

    EXPORT_REQUESTS.labels(format=req.format, delivery=delivery).inc()
    gen_timer = EXPORT_GENERATION_SECONDS.time()
    try:
        b, filename, ctype = export_bytes(obj, fmt=req.format)
    except Exception as e:
        logger.exception('Export generation failed')
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            gen_timer.__exit__(None, None, None)
        except Exception:
            pass

    # Decide storage vs streaming
    use_r2 = settings.exports_use_r2 and settings.r2_bucket and settings.r2_access_key_id and settings.r2_secret_access_key and settings.r2_endpoint_url
    if delivery == 'url' and use_r2:
        store_timer = EXPORT_R2_STORE_SECONDS.time()
        try:
            storage = get_r2_storage()
            key = f"exports/{req.run_id}/{filename}"
            signed_url = storage.store_bytes(key, b, ctype)
            EXPORT_BYTES_TOTAL.inc(len(b))
            return {
                'run_id': req.run_id,
                'filename': filename,
                'content_type': ctype,
                'url': signed_url,
                'stored': True
            }
        except Exception:
            EXPORT_R2_FAILURES.inc()
            logger.exception('R2 storage failed, falling back to streaming')
        finally:
            try:
                store_timer.__exit__(None, None, None)
            except Exception:
                pass

    # Automatic storage if large and R2 enabled, even if delivery=stream
    if use_r2:
        store_timer = EXPORT_R2_STORE_SECONDS.time()
        try:
            storage = get_r2_storage()
            key = f"exports/{req.run_id}/{filename}"
            signed_url = storage.store_bytes(key, b, ctype)
            EXPORT_BYTES_TOTAL.inc(len(b))
            return {
                'run_id': req.run_id,
                'filename': filename,
                'content_type': ctype,
                'url': signed_url,
                'stored': True,
                'reason': 'auto_stored_large_file'
            }
        except Exception:
            EXPORT_R2_FAILURES.inc()
            logger.exception('Auto store of large file failed; streaming instead')
        finally:
            try:
                store_timer.__exit__(None, None, None)
            except Exception:
                pass

    EXPORT_BYTES_TOTAL.inc(len(b))
    return Response(content=b, media_type=ctype, headers={'Content-Disposition': f'attachment; filename="{filename}"'})
