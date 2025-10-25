# backend/app/llm_client.py
from datetime import datetime
import json
import uuid
from anthropic import Anthropic
from httpx import Timeout
from typing import Dict
from fastapi import HTTPException

from app.config import settings
from app.services.extraction_prompt import SYSTEM_PROMPT, create_extraction_prompt
from app.utils.logging import logger
from app.utils.file_utils import save_raw_llm_response

class LLMClient:
    """Handle Claude API interactions"""

    def __init__(self, api_key: str, model: str, max_tokens: int, max_input_chars: int, timeout_seconds: int = 120):
        # Create timeout object for Anthropic SDK
        # read timeout is the important one for long-running API calls
        timeout = Timeout(timeout=float(timeout_seconds), read=float(timeout_seconds), write=10.0, connect=5.0)
        self.client = Anthropic(api_key=api_key, timeout=timeout)
        self.model = model
        self.max_tokens = max_tokens
        self.max_input_chars = max_input_chars
        self.timeout_seconds = timeout_seconds
    
    def extract_structured_data(self, text: str) -> Dict:
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

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=0.0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Extract text from response
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
