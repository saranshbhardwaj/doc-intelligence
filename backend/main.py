# backend/main.py
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
import os
from contextlib import asynccontextmanager
import json
import re
import asyncio

from app.utils import _normalize_llm_output
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pythonjsonlogger import jsonlogger

from app.config import settings
from app.cache import DocumentCache
from app.rate_limiter import RateLimiter
from app.document_processor import DocumentProcessor
from app.llm_client import LLMClient
from app.models import ExtractionResponse, ErrorResponse, ExtractionMetadata, FeedbackRequest, FeedbackResponse, RateLimitInfo

from app.cache_utils import list_cache_entries, clear_all_cache, preload_cache_mock
from app.analytics import SimpleAnalytics
from services.mock_responses import get_mock_cim_response

# ---------- Logging Setup ----------
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Console handler with JSON formatting
console_handler = logging.StreamHandler()
console_formatter = jsonlogger.JsonFormatter(
    '%(asctime)s %(levelname)s %(name)s %(message)s'
)
# console_handler.setFormatter(console_formatter)
# logger.addHandler(console_handler)

# File handler with rotation
from logging.handlers import RotatingFileHandler
file_handler = RotatingFileHandler(
    settings.log_dir / "app.log",
    maxBytes=10_000_000,  # 10MB
    backupCount=5,
    encoding="utf-8"
)
file_handler.setFormatter(console_formatter)
logger.addHandler(file_handler)

# ---------- Initialize Components ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run setup and teardown logic for the app lifecycle."""

    # ---------- Startup ----------
    logger.info("Application starting", extra={
        "environment": settings.environment,
        "rate_limit": f"{settings.rate_limit_uploads} uploads per {settings.rate_limit_window_hours}h",
        "max_pages": settings.max_pages,
        "max_file_size_mb": settings.max_file_size_mb
    })
    # cache.clear_expired()
    rate_limiter.clear_expired()

    # Start background cleanup task
    # cleanup_task = asyncio.create_task(periodic_cleanup())

    # yield control to the running app
    yield

    # ---------- Shutdown ----------

    # cleanup_task.cancel()  # Stop background task
    # try:
    #     await cleanup_task
    # except asyncio.CancelledError:
    #     pass
    # logger.info("Application shutting down")


app = FastAPI(
    title="Doc Intelligence API",
    version="1.0.0",
    description="Extract structured data from investment documents",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins if settings.environment == "development" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
cache = DocumentCache(
    cache_dir=settings.cache_dir,
    cache_ttl_hours=settings.cache_ttl
)

rate_limiter = RateLimiter(
    max_uploads=settings.rate_limit_uploads,
    window_hours=settings.rate_limit_window_hours
)

document_processor = DocumentProcessor(
    max_pages=settings.max_pages,
    max_file_size_bytes=settings.max_file_size_mb * 1024 * 1024
)

llm_client = LLMClient(
    api_key=settings.anthropic_api_key,
    model=settings.llm_model,
    max_tokens=settings.llm_max_tokens,
    max_input_chars=settings.llm_max_input_chars
)

analytics = SimpleAnalytics(analytics_dir=settings.analytics_dir)

# ---------- Helper Functions ----------

async def periodic_cleanup():
    """Run cleanup every hour"""
    while True:
        try:
            await asyncio.sleep(3600)  # 1 hour = 3600 seconds
            
            logger.info("Running periodic cleanup...")
            
            # Clean cache

            # cache_removed = cache.clear_expired()
            # logger.info(f"Cache cleanup: removed {cache_removed} expired entries")
            
            # Clean rate limiter
            rate_limiter.clear_expired()
            logger.info("Rate limiter cleanup completed")
            
        except asyncio.CancelledError:
            logger.info("Cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}", exc_info=True)
            # Continue running even if cleanup fails

def get_client_ip(request: Request) -> str:
    """Extract client IP from request"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host or "unknown"

def sanitize_filename(filename: str) -> str:
    """Remove unsafe characters and limit length for filenames."""
    safe = re.sub(r'[^a-zA-Z0-9_-]', '_', Path(filename).stem)
    return safe[:50]  # prevent super long names

def make_file_label(filename: str, request_id: str) -> str:
    """Generate a short, human-readable label for logging and filenames."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_name = sanitize_filename(filename)
    return f"{timestamp}_{safe_name}_{request_id[:8]}"

def save_raw_text(request_id: str, text: str, original_filename: str = "document"):
    """Save extracted text for debugging with readable filenames."""
    try:
        label = make_file_label(original_filename, request_id)
        file_path = settings.raw_dir / f"{label}.txt"
        file_path.write_text(text, encoding="utf-8")
        logger.info("Saved raw text", extra={"file_label": label, "path": str(file_path)})
    except Exception as e:
        logger.warning(f"Failed to save raw text: {e}")

def save_parsed_result(request_id: str, data: dict, original_filename: str = "document"):
    """Save parsed result for audit with readable filenames."""
    try:
        label = make_file_label(original_filename, request_id)
        file_path = settings.parsed_dir / f"{label}.json"
        file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Saved parsed result", extra={"file_label": label, "path": str(file_path)})
    except Exception as e:
        logger.warning(f"Failed to save parsed result: {e}")

def save_raw_llm_response(request_id: str, data: dict, original_filename: str = "document"):
    """Save raw llm result for audit with readable filenames."""
    try:
        label = make_file_label(original_filename, request_id)
        file_path = settings.raw_llm_dir / f"{label}.json"
        file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Saved raw llm result", extra={"file_label": label, "path": str(file_path)})
    except Exception as e:
        logger.warning(f"Failed to save parsed result: {e}")

# ---------- API Endpoints ----------

@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "ok",
        "service": "Doc Intelligence API",
        "version": "1.0.0"
    }

@app.get("/api/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "environment": settings.environment,
        "anthropic_configured": bool(settings.anthropic_api_key),
        "cache_entries": len(list(settings.parsed_dir.glob("*.json")))
    }

@app.post("/api/extract", response_model=ExtractionResponse)
async def extract_document(
    file: UploadFile = File(...),
    request: Request = None
):
    """
    Extract structured data from uploaded PDF.
    
    Limits:
    - 2 uploads per IP per 24 hours (cached results don't count)
    - Max 50 pages
    - Max 5MB file size
    """
    if settings.mock_mode:
        logger.info("🎭 Mock mode enabled - returning test data")
        mock_response = get_mock_cim_response()
        return {
            "success": True,
            "data": mock_response["data"],
            "metadata": mock_response["metadata"],
            "from_cache": False
        }
    
    request_id = str(uuid.uuid4())
    file_label = make_file_label(file.filename, request_id)
    start_time = time.time()
    client_ip = get_client_ip(request)
    
    logger.info("Request received", extra={
        "request_id": request_id,
        "file_name": file_label,
        "client_ip": client_ip
    })
    
    try:
        # Read file content
        content = await file.read()
        
        # Check cache first (before rate limiting!)
        cached_result = cache.get(content)
        
        if cached_result:
            # Cache hit - return immediately without counting against rate limit
            logger.info("Cache HIT - returning cached result", extra={
                "request_id": request_id,
                "file_name": file.filename
            })
            
            # Get current rate limit status
            _, remaining = rate_limiter.check_limit(client_ip)

            analytics.track_event(
                "cache_hit",
                client_ip=client_ip,
                filename=file.filename,
                file_size=len(content)
            )
            
            return ExtractionResponse(
                success=True,
                data=cached_result["data"],
                metadata=ExtractionMetadata(
                    request_id=request_id,
                    filename=file.filename,
                    pages=cached_result["metadata"]["pages"],
                    characters_extracted=cached_result["metadata"]["characters_extracted"],
                    processing_time_seconds=time.time() - start_time,
                    timestamp=datetime.now()
                ),
                rate_limit=RateLimitInfo(
                    remaining_uploads=remaining,
                    reset_in_hours=settings.rate_limit_window_hours,
                    limit_per_window=settings.rate_limit_uploads
                ),
                from_cache=True
            )
        
        # Cache miss - need to process
        logger.info("Cache MISS - processing document", extra={"request_id": request_id})
        
        # NOW check rate limit (only for new processing)
        is_allowed, remaining = rate_limiter.check_limit(client_ip)
        
        if not is_allowed:
            reset_time = rate_limiter.get_reset_time(client_ip)
            hours_until_reset = (reset_time - datetime.now()).total_seconds() / 3600
            
            logger.warning("Rate limit exceeded", extra={
                "request_id": request_id,
                "client_ip": client_ip
            })
            
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"You've reached the demo limit of {settings.rate_limit_uploads} uploads per {settings.rate_limit_window_hours} hours. "
                               f"Your limit resets in {hours_until_reset:.1f} hours. "
                               f"Contact us for unlimited access.",
                    "reset_in_hours": round(hours_until_reset, 1)
                }
            )
        
        # Validate file
        document_processor.validate_file(file.filename, content)
        
        # Extract text from PDF
        analytics.track_event(
            "upload_start",
            client_ip=client_ip,
            filename=file.filename,
            file_size=len(content)
        )
        text, page_count = document_processor.extract_text(content, file.filename)
        
        # Save raw text for debugging
        save_raw_text(request_id, text, file.filename)
        
        # Call LLM to extract structured data
        logger.info("Calling LLM", extra={"request_id": request_id})
        extracted_data = llm_client.extract_structured_data(text)

        save_raw_llm_response(request_id, extracted_data, file.filename)

        # Normalize LLM output to match our Pydantic models
        try:
            normalized_payload = _normalize_llm_output(extracted_data)
        except Exception as e:
            logger.exception("Normalization failed", extra={"request_id": request_id, "error": str(e)})
            normalized_payload = extracted_data  # fallback to original

        analytics.track_event(
            "upload_success",
            client_ip=client_ip,
            filename=file.filename,
            file_size=len(content)
        )
        
        # Save parsed result
        save_parsed_result(request_id, normalized_payload, file.filename)
        
        # Record upload for rate limiting (only after successful processing)
        rate_limiter.record_upload(client_ip)
        _, remaining_after = rate_limiter.check_limit(client_ip)
        
        processing_time = time.time() - start_time
        
        # Prepare response
        response_data = {
            **normalized_payload,
            "metadata": {
                "request_id": request_id,
                "filename": file.filename,
                "pages": page_count,
                "characters_extracted": len(text),
                "processing_time_seconds": processing_time
            }
        }
        
        # Cache the result
        cache.set(content, response_data)
        
        logger.info("Request completed successfully", extra={
            "request_id": request_id,
            "processing_time": round(processing_time, 2),
            "pages": page_count
        })
        
        return ExtractionResponse(
            success=True,
            **normalized_payload,
            metadata=ExtractionMetadata(
                request_id=request_id,
                filename=file.filename,
                pages=page_count,
                characters_extracted=len(text),
                processing_time_seconds=processing_time,
                timestamp=datetime.now()
            ),
            rate_limit=RateLimitInfo(
                remaining_uploads=remaining_after,
                reset_in_hours=settings.rate_limit_window_hours,
                limit_per_window=settings.rate_limit_uploads
            ),
            from_cache=False
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error", extra={
            "request_id": request_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred. Please try again or contact support. (Request ID: {request_id})"
        )
    
# ---------- Feedback Endpoint ----------

@app.post("/api/feedback", response_model=FeedbackResponse)
async def submit_feedback(feedback: FeedbackRequest, request: Request):
    """
    Submit feedback on document extraction.
    Users can rate accuracy and provide comments.
    """
    feedback_id = str(uuid.uuid4())
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("User-Agent")
    
    logger.info("Feedback received", extra={
        "feedback_id": feedback_id,
        "request_id": feedback.request_id,
        "rating": feedback.rating,
        "has_comment": bool(feedback.comment),
        "client_ip": client_ip
    })
    
    try:
        # Save feedback to file
        feedback_data = {
            "feedback_id": feedback_id,
            "request_id": feedback.request_id,
            "rating": feedback.rating,
            "accuracy_rating": feedback.accuracy_rating,
            "would_pay": feedback.would_pay,
            "comment": feedback.comment,
            "email": feedback.email,
            "client_ip": client_ip,
            "timestamp": feedback.timestamp.isoformat(),
            "user_agent": user_agent,
        }
        
        # Create feedback directory if doesn't exist
        settings.feedback_dir.mkdir(parents=True, exist_ok=True)
        
        # Save with timestamp + feedback_id
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        feedback_file = settings.feedback_dir / f"{timestamp}_{feedback_id[:8]}.json"
        feedback_file.write_text(json.dumps(feedback_data, indent=2))
        
        logger.info("Feedback saved", extra={"feedback_id": feedback_id})
        
        return FeedbackResponse(
            success=True,
            message="Thank you for your feedback! It helps us improve.",
            feedback_id=feedback_id
        )
        
    except Exception as e:
        logger.exception("Failed to save feedback", extra={"error": str(e)})
        raise HTTPException(
            status_code=500,
            detail="Failed to save feedback. Please try again."
        )
    
@app.get("/api/analytics/stats")
async def get_analytics_stats(days: int = 7):
    """
    Get basic analytics stats (for internal use).
    In production, protect this endpoint with auth.
    """
    stats = analytics.get_stats(days=days)
    return {
        "period_days": days,
        "stats": stats
    }

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