# backend/app/llm_client.py
from datetime import datetime
import json
import uuid
import asyncio
import re
from anthropic import Anthropic, BaseModel
from anthropic import AsyncAnthropic
from httpx import Timeout
from typing import Dict
from fastapi import HTTPException

from app.config import settings
from app.verticals.private_equity.extraction.prompts import (
    CIM_EXTRACTION_SYSTEM_PROMPT,
    create_extraction_prompt,
)
from app.utils.logging import logger
from app.utils.file_utils import save_raw_llm_response
from app.utils.metrics import (
    LLM_CACHE_HITS,
    LLM_CACHE_MISSES,
    LLM_REQUESTS_TOTAL,
    LLM_TOKEN_USAGE,
    LLM_COST_USD,
)
from app.utils.costs import compute_llm_cost

class LLMClient:
    """Core Anthropic Claude API client.

    Responsibilities:
    - Structured data extraction (with/without schema validation)
    - Streaming chat responses
    - JSON parsing and error recovery
    - Token usage tracking

    Note: Extraction-specific summarization moved to ExtractionLLMService.
    """

    def __init__(self, api_key: str, model: str, max_tokens: int, max_input_chars: int, timeout_seconds: int = 120):
        # Create timeout object for Anthropic SDK
        # read timeout is the important one for long-running API calls
        timeout = Timeout(timeout=float(timeout_seconds), read=float(timeout_seconds), write=10.0, connect=5.0)
        self.client = Anthropic(api_key=api_key, timeout=timeout)
        self.async_client = AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=2)

        # Expensive LLM (for structured extraction)
        self.model = model
        self.max_tokens = max_tokens
        self.max_input_chars = max_input_chars
        self.timeout_seconds = timeout_seconds

        # Cheap LLM (for summarization)
        self.cheap_model = settings.synthesis_llm_model
        self.cheap_max_tokens = settings.synthesis_llm_max_tokens
        self.cheap_timeout_seconds = settings.synthesis_llm_timeout_seconds
    
    async def extract_structured_data(
        self,
        text: str,
        context: str = None,
        system_prompt: str = None,
        use_cache: bool = False
    ) -> Dict:
        """
        Send text to Claude and get structured JSON back.

        Args:
            text: Document text to extract from (user message)
            context: Optional user-provided context to guide extraction
            system_prompt: System prompt defining extraction schema and rules.
                          For CIM extraction: use CIM_EXTRACTION_SYSTEM_PROMPT
                          For workflows: use workflow-specific system prompt (e.g., Investment Memo prompt)
                          Defaults to CIM_EXTRACTION_SYSTEM_PROMPT for backward compatibility.
            use_cache: Enable Anthropic system-level prompt caching (ephemeral, 5-min TTL)
                      Caches the system_prompt for ~90% cost savings on calls 2-N.

        Raises HTTPException if API call fails.
        """
        # Smart truncate text if too long
        if len(text) > self.max_input_chars:
            original_length = len(text)
            chars_to_cut = original_length - self.max_input_chars
            percentage_kept = (self.max_input_chars / original_length) * 100

            # Keep 80% from beginning, 20% from end (preserves intro and conclusion)
            keep_start = int(self.max_input_chars * 0.8)
            keep_end = int(self.max_input_chars * 0.2)

            text = (text[:keep_start] +
                   f"\n\n... [TRUNCATED: {chars_to_cut:,} characters removed from middle section] ...\n\n" +
                   text[-keep_end:])

            logger.warning(
                f"Document truncated: {original_length:,} → {self.max_input_chars:,} chars ({percentage_kept:.1f}% kept)",
                extra={
                    "original_length": original_length,
                    "truncated_length": self.max_input_chars,
                    "chars_removed": chars_to_cut,
                    "kept_beginning": keep_start,
                    "kept_end": keep_end
                }
            )

        # For workflows with custom system prompts, use raw text as user message
        # For CIM extraction (default), wrap text with extraction instructions
        if system_prompt is not None and system_prompt.strip():
            # Workflow mode: system prompt contains all instructions, user message is just the context
            prompt = text if text is not None else ""
            logger.debug(f"Using workflow mode: system_prompt={len(system_prompt)} chars, context={len(prompt)} chars")
        else:
            # CIM extraction mode: add extraction instructions to user message
            prompt = self._create_prompt(text, context)
            logger.debug(f"Using CIM mode: prompt={len(prompt)} chars")

        # Safety check
        if prompt is None:
            raise ValueError("Prompt cannot be None. Check text/context parameters.")

        logger.info(
            f"Calling Claude API with {len(prompt)} char prompt (timeout: {self.timeout_seconds}s)",
            extra={"prompt_length": len(prompt), "timeout": self.timeout_seconds, "has_context": bool(context)}
        )

        # Retry logic for transient API errors (rate limits, overloads, network issues)
        # Note: Workflow-level retries handle validation errors (wrong schema, missing citations)
        max_retries = 3
        retry_delay = 2  # seconds (base delay, actual delay may come from retry-after header)

        for attempt in range(max_retries):
            try:
                # Run blocking API call in thread pool to avoid blocking event loop
                # Use custom system prompt if provided (for workflows), otherwise use default CIM extraction prompt
                final_system_prompt = system_prompt if (system_prompt is not None and system_prompt.strip()) else CIM_EXTRACTION_SYSTEM_PROMPT

                # Validate inputs before API call
                if not isinstance(prompt, str):
                    raise ValueError(f"Prompt must be a string, got {type(prompt)}")
                if not isinstance(final_system_prompt, str):
                    raise ValueError(f"System prompt must be a string, got {type(final_system_prompt)}")

                # Build messages and system with optional prompt caching
                if use_cache:
                    # System-level caching (recommended by Anthropic)
                    # Cache the system prompt for maximum reuse across all calls
                    system_with_cache = [
                        {
                            "type": "text",
                            "text": final_system_prompt,
                            "cache_control": {"type": "ephemeral"}
                        }
                    ]
                    # Add assistant prefill to prioritize valid JSON completion if token limit reached
                    messages = [
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": "{"}  # Prefill to ensure valid JSON
                    ]
                    logger.debug(f"Using system-level caching with JSON prefill: system_prompt={len(final_system_prompt)} chars (cached), user_message={len(prompt)} chars")

                    message = await asyncio.to_thread(
                        self.client.messages.create,
                        model=self.model,
                        max_tokens=self.max_tokens,
                        temperature=0.0,
                        system=system_with_cache,  # Cacheable system
                        messages=messages
                    )
                else:
                    # No caching: standard format with JSON prefill
                    messages = [
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": "{"}  # Prefill to ensure valid JSON
                    ]
                    message = await asyncio.to_thread(
                        self.client.messages.create,
                        model=self.model,
                        max_tokens=self.max_tokens,
                        temperature=0.0,
                        system=final_system_prompt,  # String format
                        messages=messages
                    )
                break  # Success, exit retry loop

            except Exception as api_error:
                # Check if it's a retryable error (429 rate limit, 500/529 overloaded)
                error_str = str(api_error)
                is_retryable = (
                    "Overloaded" in error_str or
                    "overloaded_error" in error_str or
                    "Error code: 429" in error_str or  # Rate limit
                    "Error code: 529" in error_str     # Overloaded
                )

                if is_retryable and attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff: 2s, 4s, 8s

                    # Different message for rate limiting vs overload
                    if "429" in error_str:
                        logger.warning(f"API rate limit hit, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        print(f"⚠️  Rate limit exceeded, retrying in {wait_time}s...")
                    else:
                        logger.warning(f"API overloaded, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        print(f"⚠️  API overloaded, retrying in {wait_time}s...")

                    await asyncio.sleep(wait_time)  # ✅ Non-blocking sleep!
                else:
                    # Not retryable or out of retries
                    raise

        # Extract text from response (after successful retry loop)
        try:
            response_text = message.content[0].text.strip()
            usage = getattr(message, "usage", None)
            input_tokens = getattr(usage, "input_tokens", None) if usage else None
            output_tokens = getattr(usage, "output_tokens", None) if usage else None
            model_name = getattr(message, "model", self.model)
            stop_reason = getattr(message, "stop_reason", None)

            # Extract cache stats for observability
            cache_read_tokens = getattr(usage, "cache_read_input_tokens", None) if usage else None
            cache_write_tokens = getattr(usage, "cache_creation_input_tokens", None) if usage else None

            # Record Prometheus metrics
            LLM_REQUESTS_TOTAL.labels(model=model_name).inc()
            if input_tokens:
                LLM_TOKEN_USAGE.labels(model=model_name, token_type="input").inc(input_tokens)
            if output_tokens:
                LLM_TOKEN_USAGE.labels(model=model_name, token_type="output").inc(output_tokens)
            if cache_read_tokens:
                LLM_TOKEN_USAGE.labels(model=model_name, token_type="cache_read").inc(cache_read_tokens)
                LLM_CACHE_HITS.inc()
            else:
                LLM_CACHE_MISSES.inc()
            if cache_write_tokens:
                LLM_TOKEN_USAGE.labels(model=model_name, token_type="cache_write").inc(cache_write_tokens)

            # Calculate and record cost
            if input_tokens and output_tokens:
                cost = compute_llm_cost(model_name, input_tokens, output_tokens)
                if cost:
                    LLM_COST_USD.labels(model=model_name).inc(cost)

            # Prepend the prefilled "{" to complete the JSON
            response_text = "{" + response_text

            logger.info(f"Claude response: {len(response_text)} chars")

            # Log if response was truncated due to token limit
            if stop_reason == "max_tokens":
                logger.warning(
                    f"⚠️ RESPONSE TRUNCATED: Hit max_tokens limit ({self.max_tokens})",
                    extra={
                        "stop_reason": stop_reason,
                        "max_tokens": self.max_tokens,
                        "output_tokens": output_tokens,
                        "response_length": len(response_text),
                        "model": model_name
                    }
                )

            # Parse JSON from response
            parsed_json = self._parse_json_response(response_text)

            return {
                "data": parsed_json,
                "raw_text": response_text,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "model": model_name,
                    "cache_creation_input_tokens": cache_write_tokens,
                    "cache_read_input_tokens": cache_read_tokens,
                }
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            logger.error(f"Raw response: {response_text[:500]}...")

            # Save the FAILED raw response for debugging
            try:
                temp_id = str(uuid.uuid4())[:8]
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                save_raw_llm_response(
                    f"{timestamp}_FAILED_parse_{temp_id}",
                    {"raw_text": response_text, "error": str(e)},
                    "raw_llm_response_failed"
                )
                logger.info("Saved failed raw LLM response for debugging")
            except Exception as save_error:
                logger.warning(f"Failed to save error response: {save_error}")

            raise HTTPException(
                status_code=500,
                detail="The AI returned invalid data format. Please try again or contact support."
            )

        except Exception as e:
            error_msg = str(e)

            # Check if it's a timeout error
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                logger.error(
                    f"Claude API timeout after {self.timeout_seconds}s",
                    extra={"timeout": self.timeout_seconds, "error": error_msg}
                )
                raise HTTPException(
                    status_code=503,
                    detail=f"Document processing took too long (>{self.timeout_seconds}s). "
                           f"Try a shorter document or contact support for large document processing."
                )

            logger.exception(f"Claude API error: {e}")
            raise HTTPException(
                status_code=503,
                detail="AI service temporarily unavailable. Please try again in a moment."
            )

    async def extract_structured_data_with_schema(
        self,
        text: str,
        system_prompt: str,
        pydantic_model: type[BaseModel],
        use_cache: bool = False
    ) -> Dict:
        """
        Extract data with GUARANTEED schema compliance using Claude structured outputs.
        
        Args:
            text: User message content (variables + context)
            system_prompt: System prompt with extraction rules (cacheable)
            schema: JSON schema defining exact output structure
            use_cache: Enable prompt caching (recommended for workflows)
            
        Returns:
            {
                "data": <parsed_json>,  # Guaranteed to match schema
                "raw_text": <response_text>,
                "usage": {"input_tokens": int, "output_tokens": int, "model": str}
            }
            
        Raises:
            HTTPException: If API call fails (no JSON parsing errors possible!)
        """
        # Smart truncate if needed (same as extract_structured_data)
        if len(text) > self.max_input_chars:
            original_length = len(text)
            chars_to_cut = original_length - self.max_input_chars
            keep_start = int(self.max_input_chars * 0.8)
            keep_end = int(self.max_input_chars * 0.2)
            
            text = (text[:keep_start] +
                f"\n\n... [TRUNCATED: {chars_to_cut:,} characters removed] ...\n\n" +
                text[-keep_end:])
            
            logger.warning(f"Document truncated: {original_length:,} → {self.max_input_chars:,} chars")
        
        # Validate inputs
        if not isinstance(text, str):
            raise ValueError(f"Text must be a string, got {type(text)}")
        if not isinstance(system_prompt, str):
            raise ValueError(f"System prompt must be a string, got {type(system_prompt)}")
        
        logger.info(
            f"Calling Claude API with structured outputs (schema-enforced JSON)",
            extra={
                "prompt_length": len(text),
                "system_prompt_length": len(system_prompt),
                "use_cache": use_cache,
                "model": self.model
            }
        )
        
        # Retry logic for transient errors
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                # Build request with structured outputs
                if use_cache:
                    system_with_cache = [
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"}
                        }
                    ]
                    
                    message = await asyncio.to_thread(
                        self.client.messages.parse,
                        model=self.model,
                        max_tokens=self.max_tokens,
                        temperature=0.0,
                        system=system_with_cache,
                        messages=[{"role": "user", "content": text}],
                        output_format=pydantic_model
                    )
                else:
                    message = await asyncio.to_thread(
                        self.client.messages.parse,
                        model=self.model,
                        max_tokens=self.max_tokens,
                        temperature=0.0,
                        system=system_prompt,
                        messages=[{"role": "user", "content": text}],
                        output_format=pydantic_model
                    )
                
                break  # Success
                
            except Exception as api_error:
                error_str = str(api_error)
                is_retryable = (
                    "Overloaded" in error_str or
                    "overloaded_error" in error_str or
                    "Error code: 429" in error_str or
                    "Error code: 529" in error_str
                )
                
                if is_retryable and attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    logger.warning(f"API error, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    raise
        
        # Extract response
        try:
            response_text = message.content[0].text.strip()
            usage = getattr(message, "usage", None)

            # ✅ Already validated by SDK!
            parsed_output = message.parsed_output

            # Extract usage stats
            input_tokens = getattr(usage, "input_tokens", None) if usage else None
            output_tokens = getattr(usage, "output_tokens", None) if usage else None
            cache_read_tokens = getattr(usage, "cache_read_input_tokens", None) if usage else None
            cache_write_tokens = getattr(usage, "cache_creation_input_tokens", None) if usage else None
            model_name = getattr(message, "model", self.model)

            # Record Prometheus metrics
            LLM_REQUESTS_TOTAL.labels(model=model_name).inc()
            if input_tokens:
                LLM_TOKEN_USAGE.labels(model=model_name, token_type="input").inc(input_tokens)
            if output_tokens:
                LLM_TOKEN_USAGE.labels(model=model_name, token_type="output").inc(output_tokens)
            if cache_read_tokens:
                LLM_TOKEN_USAGE.labels(model=model_name, token_type="cache_read").inc(cache_read_tokens)
                LLM_CACHE_HITS.inc()
            else:
                LLM_CACHE_MISSES.inc()
            if cache_write_tokens:
                LLM_TOKEN_USAGE.labels(model=model_name, token_type="cache_write").inc(cache_write_tokens)

            # Calculate and record cost
            if input_tokens and output_tokens:
                cost = compute_llm_cost(model_name, input_tokens, output_tokens)
                if cost:
                    LLM_COST_USD.labels(model=model_name).inc(cost)

            # Log cache usage if available
            if cache_write_tokens or cache_read_tokens:
                cache_stats = {
                    "cache_creation_tokens": cache_write_tokens or 0,
                    "cache_read_tokens": cache_read_tokens or 0,
                    "regular_input_tokens": input_tokens or 0,
                }
                logger.info("Cache usage stats", extra=cache_stats)

            stop_reason = getattr(message, "stop_reason", None)
            
            # Warn if truncated (but JSON still valid!)
            if stop_reason == "max_tokens":
                logger.warning(
                    f"⚠️ Response truncated at max_tokens ({self.max_tokens})",
                    extra={"stop_reason": stop_reason, "output_tokens": getattr(usage, "output_tokens", None)}
                )
            
            return {
                "data": parsed_output.model_dump(),  # Convert to dict
                "raw_text": response_text,
                "usage": {
                    "input_tokens": getattr(usage, "input_tokens", None),
                    "output_tokens": getattr(usage, "output_tokens", None),
                    "model": getattr(message, "model", self.model),
                    "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None),
                    "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None),
                }
            }
            
        except json.JSONDecodeError as e:
            # ⚠️ This should NEVER happen with structured outputs!
            logger.error(f"IMPOSSIBLE: Structured output returned invalid JSON: {e}")
            logger.error(f"Raw response: {response_text[:500]}...")
            raise HTTPException(
                status_code=500,
                detail="Internal error: Structured output validation failed. Contact support."
            )
            
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                logger.error(f"API timeout after {self.timeout_seconds}s")
                raise HTTPException(
                    status_code=503,
                    detail=f"Processing took too long (>{self.timeout_seconds}s)."
                )
            
            logger.exception(f"Claude API error: {e}")
            raise HTTPException(
                status_code=503,
                detail="AI service temporarily unavailable."
            )

    def _parse_json_response(self, response_text: str) -> Dict:
        """Extract and parse JSON from Claude's response"""
        # Remove markdown code blocks if present
        text = response_text.strip()

        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1].strip()

        # Remove any leading/trailing whitespace
        text = text.strip()

        # If text doesn't start with { or [, try to find JSON in the response
        # This handles cases where LLM adds preamble text like "Here's the result: {..."
        if not text.startswith('{') and not text.startswith('['):
            # Find the first { or [ in the text
            json_start = min(
                (text.find('{') if '{' in text else len(text)),
                (text.find('[') if '[' in text else len(text))
            )
            if json_start < len(text):
                logger.warning(f"JSON response had preamble text (first {json_start} chars), extracting JSON only")
                text = text[json_start:]

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error at position {e.pos}: {e.msg}")
            logger.error(f"Context around error: ...{text[max(0, e.pos-100):e.pos+100]}...")
            
            # Try to fix common issues
            text = self._fix_common_json_errors(text)
            
            try:
                return json.loads(text)
            except json.JSONDecodeError as e2:
                logger.error(f"Still failed after fixes: {e2}")
                raise
    
    def _fix_common_json_errors(self, text: str) -> str:
        """Attempt to fix common JSON formatting issues"""

        # Fix citations array format: "citations": "[D1:p1]", "[D1:p3]" -> "citations": ["[D1:p1]", "[D1:p3]"]
        # Claude sometimes forgets array brackets around citations
        # Pattern: "citations": "citation1", "citation2", ... followed by comma or newline
        def fix_citations_array(match):
            # Extract all citation tokens from the matched string
            citations = re.findall(r'"(\[D\d+:p\d+\])"', match.group(0))
            if citations:
                return '"citations": [' + ', '.join(f'"{c}"' for c in citations) + ']'
            return match.group(0)

        # Match: "citations": followed by one or more quoted citation tokens (but not in array)
        # Look for pattern where citations aren't wrapped in []
        text = re.sub(
            r'"citations":\s*"(\[D\d+:p\d+\])"(?:\s*,\s*"(\[D\d+:p\d+\])")*',
            fix_citations_array,
            text
        )

        # Fix page number ranges like [11, 54-70] -> [11, 54, 70]
        # Claude sometimes uses shorthand notation for page ranges in provenance
        # We convert to just start and end (endpoints) for simplicity
        def fix_page_ranges(match):
            array_content = match.group(1)
            # Replace "number-number" with "number, number" (start, end)
            fixed = re.sub(r'(\d+)-(\d+)', r'\1, \2', array_content)
            return f'[{fixed}]'

        text = re.sub(r'\[([^\]]*\d+-\d+[^\]]*)\]', fix_page_ranges, text)

        # Fix trailing commas before closing braces/brackets
        text = re.sub(r',(\s*[}\]])', r'\1', text)

        # Fix missing commas between properties (common Claude error)
        # This is risky but can help: "value1"\n  "key2" -> "value1",\n  "key2"
        text = re.sub(r'"\s*\n\s*"', '",\n  "', text)

        # Fix truncated strings (if response was cut off)
        # Find unclosed quotes at the end
        if text.count('"') % 2 != 0:
            # Odd number of quotes - add closing quote
            last_quote = text.rfind('"')
            if last_quote > len(text) - 50:  # If near the end
                text = text[:last_quote+1] + '"' + text[last_quote+1:]

        return text
    
    def _create_prompt(self, text: str, context: str = None) -> str:
        """Create extraction prompt using the new comprehensive format"""
        return create_extraction_prompt(text, context)

    async def stream_chat(self, prompt: str):
        """
        Stream chat response from Claude (for real-time RAG chat).

        Args:
            prompt: Full prompt with context and question

        Yields:
            Dict with either:
            - {"type": "chunk", "text": str} for response chunks
            - {"type": "usage", "data": {...}} for final usage data
        """
        logger.info(
            f"Streaming chat response (prompt: {len(prompt)} chars)",
            extra={"prompt_length": len(prompt), "model": self.model}
        )

        try:
            # Use async with on the AWAITED stream
            async with self.async_client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                # Stream text chunks
                async for text in stream.text_stream:
                    yield {"type": "chunk", "text": text}

                # Get final message with usage data
                final_message = await stream.get_final_message()
                usage = getattr(final_message, "usage", None)

                if usage:
                    usage_data = {
                        "input_tokens": getattr(usage, "input_tokens", None),
                        "output_tokens": getattr(usage, "output_tokens", None),
                        "model": getattr(final_message, "model", self.model),
                        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None),
                        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None),
                    }

                    logger.info(
                        "Chat streaming complete",
                        extra={
                            "input_tokens": usage_data["input_tokens"],
                            "output_tokens": usage_data["output_tokens"],
                            "cache_read_tokens": usage_data["cache_read_input_tokens"] or 0,
                            "model": usage_data["model"]
                        }
                    )

                    yield {"type": "usage", "data": usage_data}

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Streaming chat error: {error_msg}")

            # Check for timeout
            if "timeout" in error_msg.lower():
                raise HTTPException(
                    status_code=503,
                    detail=f"Chat response took too long (>{self.timeout_seconds}s). Please try again."
                )

            raise HTTPException(
                status_code=503,
                detail="Chat service temporarily unavailable. Please try again."
            )
