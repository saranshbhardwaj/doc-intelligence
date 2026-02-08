# app/core/middleware.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.middleware.rate_limit import RateLimitMiddleware

def setup_middleware(app: FastAPI):
    """Configure all middleware"""

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting and security middleware
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,  # Allow 60 requests/minute per IP
        burst_limit=100,  # Allow bursts up to 100 requests/minute
        block_duration=300  # Block for 5 minutes if exceeded
    )
