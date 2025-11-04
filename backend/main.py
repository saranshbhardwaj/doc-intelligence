# backend/main.py
import os

from app.core.lifespan import lifespan
from app.api import extract, feedback, health, cache, jobs, users
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
app.include_router(jobs.router, tags=["jobs"])
app.include_router(users.router, tags=["users"])
app.include_router(feedback.router, tags=["feedback"])
app.include_router(cache.router, prefix="/api/cache", tags=["cache"])
app.include_router(health.router, tags=["health"])

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