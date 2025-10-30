# app/api/extract.py
from datetime import datetime
import time
import os
import tempfile
from app.api.dependencies import rate_limiter
from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from app.models import ExtractionMetadata, ExtractionResponse, RateLimitInfo, ExtractedData
from app.api.dependencies import get_client_ip, llm_client, document_processor, cache, analytics
from app.utils.file_utils import save_raw_text, save_parsed_result, save_raw_llm_response, make_file_label
from app.utils.normalization import _normalize_llm_output
from app.services.mock_responses import get_mock_cim_response
from app.services.risk_detector import detect_red_flags
from app.config import settings
from app.utils.logging import logger
import uuid

# New parser system imports
from app.services.parsers import ParserFactory
from app.utils.pdf_utils import detect_pdf_type
from app.database import SessionLocal
from app.db_models import Extraction, ParserOutput, CacheEntry

router = APIRouter()

@router.post("/api/extract", response_model=ExtractionResponse)
async def extract_document(
    file: UploadFile = File(...),
    request: Request = None
):
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

            # Apply normalization to cached data (in case normalization logic changed)
            try:
                normalized_cached = _normalize_llm_output(cached_result)
            except Exception as e:
                logger.warning(f"Failed to normalize cached data: {e}")
                normalized_cached = cached_result  # fallback to original

            # Run red flag detection on cached data (in case rules changed)
            try:
                extracted_data_obj = ExtractedData(**normalized_cached.get("data", {}))
                red_flags = detect_red_flags(extracted_data_obj)
                if "data" not in normalized_cached:
                    normalized_cached["data"] = {}
                normalized_cached["data"]["red_flags"] = red_flags
            except Exception as e:
                logger.warning(f"Red flag detection failed on cached data: {e}")
                if "data" not in normalized_cached:
                    normalized_cached["data"] = {}
                normalized_cached["data"]["red_flags"] = []

            return ExtractionResponse(
                success=True,
                data=normalized_cached.get("data", cached_result["data"]),
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

        analytics.track_event(
            "upload_start",
            client_ip=client_ip,
            filename=file.filename,
            file_size=len(content)
        )
        
        # 1. Save PDF to temporary file (parsers need file path)
        temp_pdf_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pdf', delete=False) as temp_file:
                temp_pdf_path = temp_file.name
                temp_file.write(content)

            logger.info(f"Saved PDF to temp file: {temp_pdf_path}", extra={"request_id": request_id})

            # 2. Detect PDF type (digital vs scanned)
            pdf_type = detect_pdf_type(temp_pdf_path)
            logger.info(f"PDF type detected: {pdf_type}", extra={"request_id": request_id})

            # 3. Get user tier (for now, default to "free" - TODO: get from database/auth)
            user_tier = settings.force_user_tier if settings.force_user_tier else "free"
            logger.info(f"User tier: {user_tier}", extra={"request_id": request_id})

            # 4. Check if PDF type is supported for this tier
            if not ParserFactory.is_supported(user_tier, pdf_type):
                upgrade_message = ParserFactory.get_upgrade_message(user_tier, pdf_type)
                logger.warning(f"PDF type not supported: tier={user_tier}, pdf_type={pdf_type}")
                raise HTTPException(
                    status_code=402,  # Payment Required
                    detail={
                        "error": "upgrade_required",
                        "message": upgrade_message,
                        "pdf_type": pdf_type,
                        "current_tier": user_tier
                    }
                )

            # 5. Get appropriate parser from factory
            parser = ParserFactory.get_parser(user_tier, pdf_type)
            if not parser:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to initialize document parser. Please try again."
                )

            logger.info(f"Using parser: {parser.name} (cost: ${parser.cost_per_page}/page)", extra={"request_id": request_id})

            # 6. Parse document
            parser_output = await parser.parse(temp_pdf_path, pdf_type)
            text = parser_output.text
            page_count = parser_output.page_count

            logger.info(f"Parser completed: {len(text)} chars from {page_count} pages in {parser_output.processing_time_ms}ms", extra={
                "request_id": request_id,
                "parser": parser_output.parser_name,
                "cost": parser_output.cost_usd
            })

            # 7. Store extraction metadata in database
            db = SessionLocal()
            try:
                extraction = Extraction(
                    id=request_id,
                    user_id=client_ip,  # TODO: Replace with actual user ID from auth
                    user_tier=user_tier,
                    filename=file.filename,
                    file_size_bytes=len(content),
                    page_count=page_count,
                    pdf_type=pdf_type,
                    parser_used=parser_output.parser_name,
                    processing_time_ms=parser_output.processing_time_ms,
                    cost_usd=parser_output.cost_usd,
                    status="processing",
                    from_cache=False
                )
                db.add(extraction)
                db.commit()

                # 8. Store raw parser output
                parser_db_output = ParserOutput(
                    extraction_id=request_id,
                    parser_name=parser_output.parser_name,
                    parser_version=parser_output.parser_version,
                    pdf_type=pdf_type,
                    raw_output={"text": text[:10000]},  # Store first 10k chars (full text in cache)
                    raw_output_length=len(text),
                    processing_time_ms=parser_output.processing_time_ms,
                    cost_usd=parser_output.cost_usd
                )
                db.add(parser_db_output)
                db.commit()

                logger.info("Stored extraction metadata in database", extra={"request_id": request_id})

            except Exception as db_error:
                logger.error(f"Failed to store in database: {db_error}", extra={"request_id": request_id})
                # Non-critical - continue processing
            finally:
                db.close()

        finally:
            # Clean up temp file
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                try:
                    os.unlink(temp_pdf_path)
                    logger.debug(f"Cleaned up temp file: {temp_pdf_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete temp file: {e}")

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

        # Run automated red flag detection
        try:
            # Create ExtractedData instance for type-safe detection
            extracted_data_obj = ExtractedData(**normalized_payload.get("data", {}))
            red_flags = detect_red_flags(extracted_data_obj)

            # Add red flags to normalized payload
            if "data" not in normalized_payload:
                normalized_payload["data"] = {}
            normalized_payload["data"]["red_flags"] = red_flags

            logger.info(f"Red flag detection complete: {len(red_flags)} flags found", extra={
                "request_id": request_id,
                "red_flag_count": len(red_flags)
            })
        except Exception as e:
            logger.warning(f"Red flag detection failed: {e}", extra={"request_id": request_id})
            # Non-critical - continue without red flags
            if "data" not in normalized_payload:
                normalized_payload["data"] = {}
            normalized_payload["data"]["red_flags"] = []

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

        # Update extraction status to completed in database
        db = SessionLocal()
        try:
            extraction = db.query(Extraction).filter(Extraction.id == request_id).first()
            if extraction:
                extraction.status = "completed"
                extraction.completed_at = datetime.now()
                db.commit()
                logger.debug("Updated extraction status to completed", extra={"request_id": request_id})
        except Exception as db_error:
            logger.error(f"Failed to update extraction status: {db_error}", extra={"request_id": request_id})
        finally:
            db.close()

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

        logger.info("Request completed successfully", extra={
            "request_id": request_id,
            "processing_time": round(processing_time, 2),
            "pages": page_count
        })

        # Create response (validates data with Pydantic)
        response = ExtractionResponse(
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

        # Cache ONLY after successful validation
        cache.set(content, response_data)

        return response
        
    except HTTPException:
        # Mark extraction as failed in database for known errors
        try:
            db = SessionLocal()
            extraction = db.query(Extraction).filter(Extraction.id == request_id).first()
            if extraction:
                extraction.status = "failed"
                extraction.error_message = "HTTP error occurred"
                db.commit()
            db.close()
        except:
            pass  # Don't fail on database error during error handling
        raise
    except Exception as e:
        logger.exception("Unexpected error", extra={
            "request_id": request_id,
            "error": str(e)
        })

        # Mark extraction as failed in database
        try:
            db = SessionLocal()
            extraction = db.query(Extraction).filter(Extraction.id == request_id).first()
            if extraction:
                extraction.status = "failed"
                extraction.error_message = str(e)[:500]  # Limit error message length
                db.commit()
            db.close()
        except:
            pass  # Don't fail on database error during error handling

        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred. Please try again or contact support. (Request ID: {request_id})"
        )