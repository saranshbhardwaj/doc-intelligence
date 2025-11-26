"""
Chunk Compressor for RAG

Handles chunks that exceed re-ranker token limits using:
1. LLMLingua-2 compression for narrative text
2. Smart truncation fallback for tables or over-compressed text
3. Section heading preservation

Can be toggled on/off via config for A/B testing.
"""

from typing import List, Dict, Optional
import logging
import tiktoken
from app.config import settings

logger = logging.getLogger(__name__)


class ChunkCompressor:
    """
    Compresses document chunks to fit within re-ranker token limits.

    Strategy:
    1. Count tokens in chunk
    2. If within limit → return as-is
    3. If over limit and compression enabled:
       - For narrative text → LLMLingua compression
       - For tabular text → Smart truncation
    4. If still over limit or compression disabled → Truncate
    """

    def __init__(
        self,
        token_limit: int = None,
        use_compression: bool = None,
        compression_rate: float = None,
        truncation_strategy: str = None,
        preserve_headings: bool = None
    ):
        """
        Initialize chunk compressor.

        Args:
            token_limit: Maximum tokens for re-ranker (default from settings)
            use_compression: Enable LLMLingua compression (default from settings)
            compression_rate: Compression rate 0-1 (default from settings)
            truncation_strategy: "head_tail", "head", or "tail" (default from settings)
            preserve_headings: Preserve section headings (default from settings)
        """
        self.token_limit = token_limit or settings.rag_reranker_token_limit
        self.use_compression = use_compression if use_compression is not None else settings.rag_use_compression
        self.compression_rate = compression_rate or settings.rag_compression_rate
        self.truncation_strategy = truncation_strategy or settings.rag_truncation_strategy
        self.preserve_headings = preserve_headings if preserve_headings is not None else settings.rag_preserve_headings

        # Initialize tokenizer (using cl100k_base for compatibility with most models)
        self.tokenizer = tiktoken.get_encoding("cl100k_base")

        # Lazy-load LLMLingua compressor (only if compression enabled)
        self._compressor = None
        if self.use_compression:
            self._init_compressor()

        logger.info(
            f"ChunkCompressor initialized: token_limit={self.token_limit}, "
            f"use_compression={self.use_compression}, rate={self.compression_rate}"
        )

    def _init_compressor(self):
        """Lazy initialization of LLMLingua compressor"""
        try:
            from llmlingua import PromptCompressor

            self._compressor = PromptCompressor(
                model_name=settings.rag_compression_model,
                use_llmlingua2=True  # Use LLMLingua-2
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
        Compress chunks to fit within token limits.

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
            token_count = self._count_tokens(text)

            # If within limit, no compression needed
            if token_count <= self.token_limit:
                chunk["compressed_text"] = text
                chunk["compression_applied"] = False
                chunk["original_tokens"] = token_count
                chunk["compressed_tokens"] = token_count
                compressed_chunks.append(chunk)
                continue

            # Compression/truncation needed
            compressed_text = text
            compression_method = "none"

            # Try compression for narrative text
            if self.use_compression and not is_tabular and self._compressor is not None:
                try:
                    compressed_text = self._compress_with_llmlingua(
                        text, section_heading
                    )
                    compression_method = "llmlingua"

                    # Check if still over limit (fallback to truncation)
                    compressed_token_count = self._count_tokens(compressed_text)
                    if compressed_token_count > self.token_limit:
                        logger.debug(
                            f"LLMLingua compression insufficient "
                            f"({compressed_token_count} > {self.token_limit}), "
                            f"falling back to truncation"
                        )
                        compressed_text = self._truncate(
                            compressed_text, section_heading
                        )
                        compression_method = "llmlingua+truncate"
                except Exception as e:
                    logger.warning(f"LLMLingua compression failed: {e}, using truncation")
                    compressed_text = self._truncate(text, section_heading)
                    compression_method = "truncate"
            else:
                # Truncation for tables or when compression disabled
                compressed_text = self._truncate(text, section_heading)
                compression_method = "truncate"

            # Final token count
            final_token_count = self._count_tokens(compressed_text)

            chunk["compressed_text"] = compressed_text
            chunk["compression_applied"] = True
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

        # Calculate target tokens
        target_tokens = int(self.token_limit * self.compression_rate)

        # Compress using LLMLingua-2
        result = self._compressor.compress_prompt(
            text_to_compress,
            rate=self.compression_rate,
            target_token=target_tokens,
            force_tokens=['\n', '?', '.', '!', ':', ';']  # Preserve punctuation
        )

        compressed_text = result.get("compressed_prompt", text_to_compress)

        # Re-add heading
        if heading_prefix:
            compressed_text = heading_prefix + compressed_text

        return compressed_text

    def _truncate(
        self,
        text: str,
        section_heading: Optional[str] = None
    ) -> str:
        """
        Truncate text to fit within token limit.

        Strategies:
        - "head_tail": Keep first 60% and last 40% of tokens
        - "head": Keep first N tokens
        - "tail": Keep last N tokens

        Args:
            text: Text to truncate
            section_heading: Optional section heading to preserve

        Returns:
            Truncated text
        """
        # Preserve heading if requested
        heading_prefix = ""
        text_to_truncate = text
        heading_tokens = 0

        if self.preserve_headings and section_heading:
            heading_prefix = f"{section_heading}\n"
            heading_tokens = self._count_tokens(heading_prefix)
            # Remove heading from text if it starts with it
            if text.startswith(section_heading):
                text_to_truncate = text[len(section_heading):].lstrip()

        # Available tokens for content (after heading)
        available_tokens = self.token_limit - heading_tokens

        # Tokenize text
        tokens = self.tokenizer.encode(text_to_truncate)

        if len(tokens) <= available_tokens:
            return heading_prefix + text_to_truncate

        # Apply truncation strategy
        if self.truncation_strategy == "head_tail":
            # Keep first 60% and last 40%
            head_count = int(available_tokens * 0.6)
            tail_count = int(available_tokens * 0.4)

            head_tokens = tokens[:head_count]
            tail_tokens = tokens[-tail_count:]

            truncated_text = (
                self.tokenizer.decode(head_tokens) +
                "\n...[truncated]...\n" +
                self.tokenizer.decode(tail_tokens)
            )
        elif self.truncation_strategy == "tail":
            # Keep last N tokens
            truncated_tokens = tokens[-available_tokens:]
            truncated_text = "...[truncated]...\n" + self.tokenizer.decode(truncated_tokens)
        else:  # "head" or default
            # Keep first N tokens
            truncated_tokens = tokens[:available_tokens]
            truncated_text = self.tokenizer.decode(truncated_tokens) + "\n...[truncated]..."

        return heading_prefix + truncated_text

    def _count_tokens(self, text: str) -> int:
        """
        Count tokens in text.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        return len(self.tokenizer.encode(text))
