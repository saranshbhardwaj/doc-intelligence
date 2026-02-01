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

from app.core.lifespan import lifespan
from app.api import extractions, feedback, health, cache, jobs, users, chat, workflows, metrics
from app.core.middleware import setup_middleware
from fastapi import FastAPI

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