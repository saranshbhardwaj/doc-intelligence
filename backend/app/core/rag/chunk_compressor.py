"""
Chunk Compressor for RAG

Compresses narrative text using LLMLingua-2 to reduce token count and LLM costs.

Pure compression function - always compresses when called.
Caller decides when compression is needed.

Can be toggled on/off via config for A/B testing.
"""

from typing import List, Dict, Optional
import logging
from app.config import settings
from app.utils.token_utils import count_tokens

logger = logging.getLogger(__name__)


class ChunkCompressor:
    """
    Compresses document chunks using LLMLingua-2.

    Pure compression function - always compresses when called.
    Caller decides when compression is needed (no token limit checking here).

    Strategy:
    - For narrative text: LLMLingua-2 compression
    - For tabular text: Skip compression (tables should not be compressed)
    """

    def __init__(
        self,
        use_compression: bool = None,
        compression_rate: float = None,
        preserve_headings: bool = None
    ):
        """
        Initialize chunk compressor.

        Args:
            use_compression: Enable LLMLingua compression (default from settings)
            compression_rate: Target compression rate 0-1 (default from settings)
            preserve_headings: Preserve section headings (default from settings)
        """
        self.use_compression = use_compression if use_compression is not None else settings.rag_use_compression
        self.compression_rate = compression_rate or settings.rag_compression_rate
        self.preserve_headings = preserve_headings if preserve_headings is not None else settings.rag_preserve_headings

        # Lazy-load LLMLingua compressor (only if compression enabled)
        self._compressor = None
        if self.use_compression:
            self._init_compressor()

        logger.info(
            f"ChunkCompressor initialized: use_compression={self.use_compression}, "
            f"rate={self.compression_rate}"
        )

    def _init_compressor(self):
        """Lazy initialization of LLMLingua compressor"""
        try:
            from llmlingua import PromptCompressor

            self._compressor = PromptCompressor(
                model_name=settings.rag_compression_model,
                use_llmlingua2=True,  # Use LLMLingua-2
                device_map="cpu"  # Force CPU usage (Docker containers typically don't have GPU)
            )
            logger.info(f"LLMLingua compressor loaded: {settings.rag_compression_model}")
        except ImportError:
            logger.error(
                "llmlingua package not installed. Install with: pip install llmlingua"
            )
            self.use_compression = False
        except Exception as e:
            logger.error(f"Failed to initialize LLMLingua compressor: {e}", exc_info=True)
            self.use_compression = False

    def compress_chunks(self, chunks: List[Dict]) -> List[Dict]:
        """
        Compress chunks using LLMLingua-2.

        Pure compression function - always compresses when called.
        Caller is responsible for deciding whether to call this.

        Skips tabular chunks (tables should not be compressed).

        Args:
            chunks: List of chunk dicts with "text" field

        Returns:
            List of chunks with "compressed_text" field added
        """
        compressed_chunks = []

        for chunk in chunks:
            text = chunk.get("text", "")
            is_tabular = chunk.get("is_tabular", False)
            section_heading = chunk.get("section_heading", "")

            # Count tokens in original text
            token_count = count_tokens(text)

            # Compress narrative text only
            compressed_text = text
            compression_method = "none"

            if self.use_compression and not is_tabular and self._compressor is not None:
                try:
                    compressed_text = self._compress_with_llmlingua(
                        text, section_heading
                    )
                    compression_method = "llmlingua"
                except Exception as e:
                    logger.warning(f"LLMLingua compression failed: {e}, using original text")
                    compressed_text = text
                    compression_method = "failed"

            # Final token count
            final_token_count = count_tokens(compressed_text)

            chunk["compressed_text"] = compressed_text
            chunk["compression_applied"] = compression_method != "none"
            chunk["compression_method"] = compression_method
            chunk["original_tokens"] = token_count
            chunk["compressed_tokens"] = final_token_count
            chunk["compression_ratio"] = final_token_count / token_count if token_count > 0 else 1.0

            compressed_chunks.append(chunk)

            logger.debug(
                f"Compressed chunk: {token_count} → {final_token_count} tokens "
                f"({compression_method}), ratio={chunk['compression_ratio']:.2f}"
            )

        return compressed_chunks

    def _compress_with_llmlingua(
        self,
        text: str,
        section_heading: Optional[str] = None
    ) -> str:
        """
        Compress text using LLMLingua-2.

        Args:
            text: Text to compress
            section_heading: Optional section heading to preserve

        Returns:
            Compressed text
        """
        if self._compressor is None:
            return text

        # Preserve heading if requested
        heading_prefix = ""
        text_to_compress = text
        if self.preserve_headings and section_heading:
            heading_prefix = f"{section_heading}\n"
            # Remove heading from text if it starts with it
            if text.startswith(section_heading):
                text_to_compress = text[len(section_heading):].lstrip()

        # Compress using LLMLingua-2 with target compression rate
        result = self._compressor.compress_prompt(
            text_to_compress,
            rate=self.compression_rate,
            force_tokens=['\n', '?', '.', '!', ':', ';']  # Preserve punctuation
        )

        compressed_text = result.get("compressed_prompt", text_to_compress)

        # Re-add heading
        if heading_prefix:
            compressed_text = heading_prefix + compressed_text

        return compressed_text

    def compress_text_to_token_limit(
        self,
        text: str,
        target_tokens: int,
        section_heading: Optional[str] = None
    ) -> str:
        """
        Compress text to fit within a target token limit.

        Used by re-ranker to compress chunks for cross-encoder scoring (512 token limit).

        Args:
            text: Text to compress
            target_tokens: Target token count (e.g., 512 for cross-encoder)
            section_heading: Optional section heading to preserve

        Returns:
            Compressed text fitting within target_tokens
        """
        if not text:
            return text

        # Count tokens in original text
        original_tokens = count_tokens(text)

        # If already within limit, return as-is
        if original_tokens <= target_tokens:
            return text

        # If compression disabled, fall back to truncation
        if not self.use_compression or self._compressor is None:
            logger.debug(
                f"Compression disabled, truncating {original_tokens} → {target_tokens} tokens"
            )
            from app.utils.token_utils import truncate_to_token_limit
            return truncate_to_token_limit(text, target_tokens)

        # Calculate required compression rate
        # Add 10% buffer to ensure we hit target (LLMLingua is approximate)
        target_rate = (target_tokens * 0.9) / original_tokens
        target_rate = max(0.1, min(target_rate, 1.0))  # Clamp to [0.1, 1.0]

        logger.debug(
            f"Compressing text: {original_tokens} → {target_tokens} tokens "
            f"(rate={target_rate:.2f})"
        )

        try:
            # Preserve heading if requested
            heading_prefix = ""
            text_to_compress = text
            if self.preserve_headings and section_heading:
                heading_prefix = f"{section_heading}\n"
                if text.startswith(section_heading):
                    text_to_compress = text[len(section_heading):].lstrip()

            # Compress using LLMLingua-2 with calculated rate
            result = self._compressor.compress_prompt(
                text_to_compress,
                rate=target_rate,
                force_tokens=['\n', '?', '.', '!', ':', ';']
            )

            compressed_text = result.get("compressed_prompt", text_to_compress)

            # Re-add heading
            if heading_prefix:
                compressed_text = heading_prefix + compressed_text

            # Verify we hit target (if not, truncate as fallback)
            final_tokens = count_tokens(compressed_text)
            if final_tokens > target_tokens:
                logger.warning(
                    f"LLMLingua compression exceeded target: {final_tokens} > {target_tokens}, "
                    "truncating as fallback"
                )
                from app.utils.token_utils import truncate_to_token_limit
                compressed_text = truncate_to_token_limit(compressed_text, target_tokens)
                final_tokens = target_tokens

            logger.debug(
                f"Compression complete: {original_tokens} → {final_tokens} tokens "
                f"({(final_tokens/original_tokens)*100:.1f}%)"
            )

            return compressed_text

        except Exception as e:
            logger.warning(
                f"LLMLingua compression failed: {e}, falling back to truncation"
            )
            from app.utils.token_utils import truncate_to_token_limit
            return truncate_to_token_limit(text, target_tokens)
