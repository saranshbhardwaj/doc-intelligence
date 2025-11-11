"""Redis Pub/Sub utilities for real-time job progress.

Design goals:
 - Decouple persistence (database) from streaming delivery (SSE)
 - Provide lightweight, fire-and-forget publishing from task/Tracker code
 - Avoid blocking the event loop if Redis is slow/unavailable
 - Offer defensive fallbacks: silent failure on publish, optional health check

Message schema (JSON string published to Redis channel):
{
  "event": "progress" | "error" | "complete" | "end",
  "payload": { ... arbitrary fields ... }
}

Channel naming convention: job:progress:<job_id>

Consumers (SSE endpoint) subscribe to channel and forward each message as SSE event.
"""
from __future__ import annotations
import json
from typing import Any, Dict
from functools import lru_cache
from urllib.parse import urlparse

import redis  # Provided transitively via celery[redis]

from app.config import settings
from app.utils.logging import logger


def job_channel(job_id: str) -> str:
    return f"job:progress:{job_id}"


@lru_cache(maxsize=1)
def _get_connection_params() -> Dict[str, Any]:
    """Derive Redis connection params from celery broker URL or defaults."""
    url = urlparse(settings.celery_broker_url)
    host = url.hostname or "localhost"
    port = url.port or 6379
    db = int(url.path[1:] or 0) if url.path else 0
    return {"host": host, "port": port, "db": db, "decode_responses": True}


def get_redis() -> redis.Redis:
    return redis.Redis(**_get_connection_params())


def publish_event(job_id: str, event: str, payload: Dict[str, Any]) -> None:
    """Publish a job progress event.

    Defensive strategy:
      - Wrap in try/except; log at DEBUG on success, WARNING on failure
      - Never raise to caller (streaming shouldn't break core logic)
    """
    message = {"event": event, "payload": payload}
    channel = job_channel(job_id)
    try:
        redis_client = get_redis()
        redis_client.publish(channel, json.dumps(message))
        logger.info(f"✅ Published pubsub event: {event}", extra={"job_id": job_id, "event": event, "channel": channel})
    except Exception as e:
        logger.warning(f"❌ Redis publish failed: {event}", extra={"job_id": job_id, "event": event, "error": str(e)})


def safe_subscribe(job_id: str):
    """Return a Redis PubSub object subscribed to the job channel.

    Caller is responsible for closing via pubsub.close().
    """
    redis_client = get_redis()
    pubsub = redis_client.pubsub()
    channel = job_channel(job_id)
    try:
        pubsub.subscribe(channel)
        logger.info(f"🎧 Subscribed to Redis pub/sub channel: {channel}", extra={"job_id": job_id, "channel": channel})
    except Exception as e:
        logger.error(f"❌ Failed to subscribe to pubsub channel: {channel}", extra={"job_id": job_id, "channel": channel, "error": str(e)})
    return pubsub
