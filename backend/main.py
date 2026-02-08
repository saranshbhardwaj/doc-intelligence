# backend/main.py
import os
import sys

# Debug configuration - attach debugpy if DEBUG is truthy
def _is_debug_enabled() -> bool:
    return os.getenv("DEBUG", "").strip().lower() in {"1", "true", "yes", "y", "on"}

def _should_wait_for_debugger() -> bool:
    return os.getenv("DEBUG_WAIT", "").strip().lower() in {"1", "true", "yes", "y", "on"}

if _is_debug_enabled():
    try:
        import debugpy
        debugpy.listen(("0.0.0.0", 5678))
        print("⏸️  Debugger listening on 0.0.0.0:5678", file=sys.stderr)
        if _should_wait_for_debugger():
            print("⏳ Waiting for debugger to attach...", file=sys.stderr)
            debugpy.wait_for_client()
    except Exception as e:
        print(f"Failed to initialize debugpy: {e}", file=sys.stderr)

# Initialize Prometheus multiprocess mode BEFORE any imports that might create metrics
# This MUST happen before importing any module that uses prometheus_client
# Otherwise metrics will be created in single-process mode and won't be shared
# clear_on_startup=True: API is the "leader" and cleans stale files from dead processes
from app.core.metrics_setup import setup_prometheus_multiproc_dir
setup_prometheus_multiproc_dir(clear_on_startup=True)

# Now safe to import modules that may transitively import app.utils.metrics
from app.core.lifespan import lifespan
from app.api import extractions, feedback, health, cache, jobs, users, chat, workflows, metrics
from app.api.admin import router as admin_router
from app.core.middleware import setup_middleware
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

# Import vertical routers
from app.verticals.private_equity.api.router import router as pe_router
from app.verticals.real_estate.api.router import router as re_router

app = FastAPI(
    title="Doc Intelligence API",
    version="1.0.0",
    description="Extract structured data from investment documents",
    lifespan=lifespan
)

# Setup middleware
setup_middleware(app)

# Setup Prometheus instrumentation for automatic HTTP metrics
# Provides: http_requests_total, http_request_duration_seconds, http_requests_in_progress
# Note: We use our custom /metrics endpoint (app.api.metrics) for multiprocess support
Instrumentator().instrument(app)  # Don't call .expose() - we have custom endpoint

# Register legacy API routes (shared/backwards compatibility)
app.include_router(extractions.router, tags=["extraction"])  # Unified endpoint (handles both sync and async)
app.include_router(chat.router)  # Chat Mode endpoints
app.include_router(workflows.router, tags=["workflows"])
app.include_router(jobs.router, tags=["jobs"])
app.include_router(users.router, tags=["users"])
app.include_router(feedback.router, tags=["feedback"])
app.include_router(cache.router, prefix="/api/cache", tags=["cache"])
app.include_router(health.router, tags=["health"])
app.include_router(metrics.router, tags=["metrics"])  # /metrics for Prometheus

# Register admin API routes (admin-only endpoints)
app.include_router(admin_router)  # Admin: /api/admin/*

# Register vertical-specific API routes
app.include_router(pe_router, prefix="/api/v1")  # Private Equity: /api/v1/pe/*
app.include_router(re_router, prefix="/api/v1")  # Real Estate: /api/v1/re/*

# ---------- Run ----------

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )