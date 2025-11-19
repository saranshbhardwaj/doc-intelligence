# backend/main.py
import os

from app.core.lifespan import lifespan
from app.api import extract, feedback, health, cache, jobs, users, chat, workflows, metrics
from app.core.middleware import setup_middleware
from fastapi import FastAPI


app = FastAPI(
    title="Doc Intelligence API",
    version="1.0.0",
    description="Extract structured data from investment documents",
    lifespan=lifespan
)

# Setup middleware
setup_middleware(app)

# Register API routes
app.include_router(extract.router, tags=["extraction"])  # Unified endpoint (handles both sync and async)
app.include_router(chat.router)  # Chat Mode endpoints
app.include_router(workflows.router, tags=["workflows"])
app.include_router(jobs.router, tags=["jobs"])
app.include_router(users.router, tags=["users"])
app.include_router(feedback.router, tags=["feedback"])
app.include_router(cache.router, prefix="/api/cache", tags=["cache"])
app.include_router(health.router, tags=["health"])
app.include_router(metrics.router, tags=["metrics"])  # /metrics for Prometheus

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