# backend/app/llm_client.py
from datetime import datetime
import json
import uuid
import asyncio
from anthropic import Anthropic
from httpx import Timeout
from typing import Dict
from fastapi import HTTPException

from app.config import settings
from app.services.extraction_prompt import SYSTEM_PROMPT, create_extraction_prompt
from app.services.summary_prompt import SUMMARY_SYSTEM_PROMPT, create_summary_prompt, create_batch_summary_prompt
from app.utils.logging import logger
from app.utils.file_utils import save_raw_llm_response

class LLMClient:
    """Handle Claude API interactions for both expensive and cheap LLM calls"""

    def __init__(self, api_key: str, model: str, max_tokens: int, max_input_chars: int, timeout_seconds: int = 120):
        # Create timeout object for Anthropic SDK
        # read timeout is the important one for long-running API calls
        timeout = Timeout(timeout=float(timeout_seconds), read=float(timeout_seconds), write=10.0, connect=5.0)
        self.client = Anthropic(api_key=api_key, timeout=timeout)

        # Expensive LLM (for structured extraction)
        self.model = model
        self.max_tokens = max_tokens
        self.max_input_chars = max_input_chars
        self.timeout_seconds = timeout_seconds

        # Cheap LLM (for summarization)
        self.cheap_model = settings.cheap_llm_model
        self.cheap_max_tokens = settings.cheap_llm_max_tokens
        self.cheap_timeout_seconds = settings.cheap_llm_timeout_seconds
    
    async def extract_structured_data(self, text: str) -> Dict:
        """
        Send text to Claude and get structured JSON back.
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
        
        prompt = self._create_prompt(text)

        logger.info(
            f"Calling Claude API with {len(prompt)} char prompt (timeout: {self.timeout_seconds}s)",
            extra={"prompt_length": len(prompt), "timeout": self.timeout_seconds}
        )

        # Retry logic for API overloads and rate limits
        max_retries = 3
        retry_delay = 2  # seconds

        for attempt in range(max_retries):
            try:
                # Run blocking API call in thread pool to avoid blocking event loop
                message = await asyncio.to_thread(
                    self.client.messages.create,
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=0.0,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}]
                )
                break  # Success, exit retry loop

            except Exception as api_error:
                # Check if it's a retryable error (500 overloaded, 529 rate limit)
                error_str = str(api_error)
                is_retryable = "Overloaded" in error_str or "overloaded_error" in error_str or "Error code: 529" in error_str

                if is_retryable and attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff: 2s, 4s, 8s
                    logger.warning(f"API overloaded, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    print(f"⚠️  API overloaded, retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)  # ✅ Non-blocking sleep!
                else:
                    # Not retryable or out of retries
                    raise

        # Extract text from response (after successful retry loop)
        try:
            response_text = message.content[0].text.strip()

            logger.info(f"Claude response: {len(response_text)} chars")

            # Parse JSON from response
            parsed_json = self._parse_json_response(response_text)

            return parsed_json

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
        import re

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
    
    def _create_prompt(self, text: str) -> str:
      """Create extraction prompt using the new comprehensive format"""
      return create_extraction_prompt(text)

    async def summarize_chunk(self, chunk_text: str) -> str:
        """Async wrapper to summarize a single chunk using thread offload."""
        return await asyncio.to_thread(self._summarize_chunk_sync, chunk_text)

    def _summarize_chunk_sync(self, chunk_text: str) -> str:
        prompt = create_summary_prompt(chunk_text)
        logger.info(
            f"Calling cheap LLM ({self.cheap_model}) for chunk summary",
            extra={"prompt_length": len(prompt)}
        )
        try:
            message = self.client.messages.create(
                model=self.cheap_model,
                max_tokens=self.cheap_max_tokens,
                temperature=0.0,
                system=SUMMARY_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )
            summary = message.content[0].text.strip()
            logger.debug(f"Cheap LLM summary: {len(summary)} chars")
            return summary
        except Exception as e:
            logger.error(f"Cheap LLM summarization failed: {e}")
            logger.warning("Falling back to original chunk text")
            return chunk_text

    async def summarize_chunks_batch(self, chunks: list[dict]) -> list[str]:
        """Async wrapper for batch summarization using thread offload."""
        return await asyncio.to_thread(self._summarize_chunks_batch_sync, chunks)

    def _summarize_chunks_batch_sync(self, chunks: list[dict]) -> list[str]:
        if not chunks:
            return []
        prompt = create_batch_summary_prompt(chunks)
        logger.info(
            f"Calling cheap LLM ({self.cheap_model}) for batch summary of {len(chunks)} chunks",
            extra={"prompt_length": len(prompt), "chunk_count": len(chunks)}
        )
        try:
            message = self.client.messages.create(
                model=self.cheap_model,
                max_tokens=self.cheap_max_tokens,
                temperature=0.0,
                system=SUMMARY_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )
            batch_summary = message.content[0].text.strip()
            logger.info(f"Batch summary received: {len(batch_summary)} chars")
            return self._parse_batch_summaries(batch_summary, len(chunks))
        except Exception as e:
            logger.error(f"Batch summarization failed: {e}")
            logger.warning("Falling back to original chunk texts")
            return [chunk["text"] for chunk in chunks]

    def _parse_batch_summaries(self, batch_output: str, expected_count: int) -> list[str]:
        """Parse individual summaries from batch output.

        Expected format:
        Page 1: [summary]
        Key Numbers: [numbers]

        Page 2: [summary]
        Key Numbers: [numbers]
        """
        import re

        summaries = []
        # Split by "Page N:" pattern
        page_pattern = r"Page \d+:\s*(.+?)(?=Page \d+:|$)"
        matches = re.findall(page_pattern, batch_output, re.DOTALL)

        if len(matches) >= expected_count:
            summaries = [match.strip() for match in matches[:expected_count]]
        else:
            # Parsing failed, return full output split by double newlines
            logger.warning(f"Failed to parse {expected_count} summaries, got {len(matches)}. Using fallback parsing.")
            parts = batch_output.split("\n\n")
            summaries = parts[:expected_count]
            # Pad with empty strings if needed
            while len(summaries) < expected_count:
                summaries.append("")

        return summaries
