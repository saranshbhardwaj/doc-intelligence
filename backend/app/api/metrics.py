from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", summary="Prometheus metrics scrape endpoint")
def metrics_root():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
