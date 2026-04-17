# backend/app/services/embeddings/openai_provider.py
"""
OpenAI embedding provider (paid API).
Uses OpenAI's embedding models via API.
"""
import time
from typing import List
from openai import OpenAI
from app.core.embeddings.base import EmbeddingProvider
from app.utils.logging import logger
from app.utils.metrics import (
    EMBEDDING_REQUESTS_TOTAL,
    EMBEDDING_FAILURES_TOTAL,
    EMBEDDING_RETRIES_TOTAL,
    EMBEDDING_LATENCY_SECONDS,
    EMBEDDING_TOKEN_USAGE,
)


class OpenAIEmbedding(EmbeddingProvider):
    """
    OpenAI embedding provider.

    Pros:
    - High quality embeddings
    - State-of-the-art for semantic search
    - Large context window (8191 tokens)

    Cons:
    - Costs money ($0.02 per 1M tokens for text-embedding-3-small)
    - Requires internet connection
    - API latency
    """

    # Default (maximum) dimensions per model
    MAX_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,  # Legacy model (does not support dimensions param)
    }

    # Models that support the `dimensions` API parameter (Matryoshka dimensionality reduction)
    SUPPORTS_DIMENSIONS_PARAM = {"text-embedding-3-small", "text-embedding-3-large"}

    def __init__(self, api_key: str, model_name: str = "text-embedding-3-small", dimensions: int = None):
        """
        Initialize OpenAI embedding client.

        Args:
            api_key: OpenAI API key
            model_name: OpenAI embedding model name
            dimensions: Output dimension (reduced via Matryoshka). Only supported by v3 models.
                If None, uses the model's default max dimension.
        """
        if not api_key:
            raise ValueError("OpenAI API key is required for OpenAI embeddings")

        self._model_name = model_name
        self.client = OpenAI(api_key=api_key)

        if model_name not in self.MAX_DIMENSIONS:
            raise ValueError(f"Unknown OpenAI model: {model_name}. Supported: {list(self.MAX_DIMENSIONS.keys())}")

        max_dim = self.MAX_DIMENSIONS[model_name]

        # Use custom dimensions if provided, otherwise use model default
        if dimensions is not None:
            if model_name not in self.SUPPORTS_DIMENSIONS_PARAM:
                raise ValueError(f"Model {model_name} does not support custom dimensions")
            if dimensions < 1 or dimensions > max_dim:
                raise ValueError(f"dimensions must be between 1 and {max_dim} for {model_name}, got {dimensions}")
            self._dimension = dimensions
            self._use_dimensions_param = True
        else:
            self._dimension = max_dim
            self._use_dimensions_param = False

        logger.info(f"OpenAI embeddings initialized: {model_name} (dimension: {self._dimension})")

    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text to embed

        Returns:
            List of floats (embedding vector)

        Raises:
            ValueError: If text is invalid
            RuntimeError: If API call fails
        """
        # Edge case: Validate text input
        if not isinstance(text, str):
            raise ValueError(f"text must be a string, got {type(text).__name__}")

        if not text or not text.strip():
            logger.warning("Empty text provided for embedding, returning zero vector")
            return [0.0] * self._dimension

        # Retry logic for transient API errors (rate limits, overloads)
        max_retries = 3
        retry_delay = 2  # seconds base delay

        for attempt in range(max_retries):
            request_start = time.time()
            try:
                create_kwargs = {"model": self._model_name, "input": text}
                if self._use_dimensions_param:
                    create_kwargs["dimensions"] = self._dimension
                response = self.client.embeddings.create(**create_kwargs)

                # Record metrics
                elapsed = time.time() - request_start
                EMBEDDING_LATENCY_SECONDS.labels(model=self._model_name).observe(elapsed)
                EMBEDDING_REQUESTS_TOTAL.labels(model=self._model_name).inc()

                usage = getattr(response, "usage", None)
                if usage:
                    total_tokens = getattr(usage, "total_tokens", 0)
                    if total_tokens:
                        EMBEDDING_TOKEN_USAGE.labels(model=self._model_name).inc(total_tokens)

                # Validate API response
                if not response or not response.data:
                    raise RuntimeError("OpenAI API returned empty response")
                if len(response.data) == 0:
                    raise RuntimeError("OpenAI API returned no embeddings")

                embedding = response.data[0].embedding

                if len(embedding) != self._dimension:
                    logger.warning(
                        f"OpenAI embedding dimension mismatch: expected {self._dimension}, got {len(embedding)}"
                    )

                return embedding

            except Exception as e:
                error_str = str(e)
                is_retryable = (
                    "429" in error_str or
                    "529" in error_str or
                    "Overloaded" in error_str or
                    "overloaded_error" in error_str
                )

                if "429" in error_str:
                    error_type = "rate_limit"
                elif "529" in error_str or "Overloaded" in error_str:
                    error_type = "overload"
                elif "timeout" in error_str.lower():
                    error_type = "timeout"
                else:
                    error_type = "other"

                if is_retryable and attempt < max_retries - 1:
                    EMBEDDING_RETRIES_TOTAL.labels(model=self._model_name).inc()
                    wait_time = retry_delay * (2 ** attempt)  # 2s, 4s, 8s
                    logger.warning(
                        f"OpenAI embedding API error ({error_type}), retrying in {wait_time}s "
                        f"(attempt {attempt + 1}/{max_retries}): {e}"
                    )
                    time.sleep(wait_time)
                else:
                    EMBEDDING_REQUESTS_TOTAL.labels(model=self._model_name).inc()
                    EMBEDDING_FAILURES_TOTAL.labels(model=self._model_name, error_type=error_type).inc()
                    logger.error(
                        f"OpenAI API embedding failed: {e}",
                        extra={"model": self._model_name, "text_length": len(text), "attempts": attempt + 1},
                        exc_info=True
                    )
                    raise RuntimeError(f"Failed to generate OpenAI embedding: {e}") from e

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (batched API call).

        OpenAI supports up to 2048 texts per batch.

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors

        Raises:
            ValueError: If texts is invalid
            RuntimeError: If API call fails
        """
        # Edge case: Validate texts input
        if not isinstance(texts, list):
            raise ValueError(f"texts must be a list, got {type(texts).__name__}")

        if not texts:
            logger.warning("Empty texts list provided for batch embedding")
            return []

        # Edge case: Filter out empty/invalid texts and track positions
        valid_texts = []
        valid_indices = []
        for i, text in enumerate(texts):
            if isinstance(text, str) and text and text.strip():
                valid_texts.append(text)
                valid_indices.append(i)
            else:
                logger.warning(f"Skipping invalid text at index {i} in batch")

        if not valid_texts:
            logger.warning("No valid texts in batch after filtering")
            return [[0.0] * self._dimension] * len(texts)

        # OpenAI supports batch embedding (up to 2048 items)
        # Split into chunks if needed
        max_batch_size = 2048
        valid_embeddings = []

        try:
            for i in range(0, len(valid_texts), max_batch_size):
                batch = valid_texts[i:i + max_batch_size]

                # Retry logic for each batch chunk
                batch_num = i // max_batch_size + 1
                max_retries = 3
                retry_delay = 2

                for attempt in range(max_retries):
                    request_start = time.time()
                    try:
                        create_kwargs = {"model": self._model_name, "input": batch}
                        if self._use_dimensions_param:
                            create_kwargs["dimensions"] = self._dimension
                        response = self.client.embeddings.create(**create_kwargs)

                        # Record metrics
                        elapsed = time.time() - request_start
                        EMBEDDING_LATENCY_SECONDS.labels(model=self._model_name).observe(elapsed)
                        EMBEDDING_REQUESTS_TOTAL.labels(model=self._model_name).inc()

                        usage = getattr(response, "usage", None)
                        if usage:
                            total_tokens = getattr(usage, "total_tokens", 0)
                            if total_tokens:
                                EMBEDDING_TOKEN_USAGE.labels(model=self._model_name).inc(total_tokens)

                        # Validate API response
                        if not response or not response.data:
                            raise RuntimeError(f"OpenAI API returned empty response for batch {batch_num}")
                        if len(response.data) != len(batch):
                            raise RuntimeError(
                                f"OpenAI API returned {len(response.data)} embeddings "
                                f"but expected {len(batch)} for batch {batch_num}"
                            )

                        batch_embeddings = [item.embedding for item in response.data]
                        valid_embeddings.extend(batch_embeddings)
                        break  # Success, exit retry loop

                    except Exception as batch_error:
                        error_str = str(batch_error)
                        is_retryable = (
                            "429" in error_str or "529" in error_str or
                            "Overloaded" in error_str or "overloaded_error" in error_str
                        )

                        if "429" in error_str:
                            error_type = "rate_limit"
                        elif "529" in error_str or "Overloaded" in error_str:
                            error_type = "overload"
                        else:
                            error_type = "other"

                        if is_retryable and attempt < max_retries - 1:
                            EMBEDDING_RETRIES_TOTAL.labels(model=self._model_name).inc()
                            wait_time = retry_delay * (2 ** attempt)
                            logger.warning(
                                f"OpenAI embedding batch API error ({error_type}), retrying in {wait_time}s "
                                f"(attempt {attempt + 1}/{max_retries})"
                            )
                            time.sleep(wait_time)
                        else:
                            EMBEDDING_REQUESTS_TOTAL.labels(model=self._model_name).inc()
                            EMBEDDING_FAILURES_TOTAL.labels(model=self._model_name, error_type=error_type).inc()
                            logger.error(
                                f"OpenAI API batch embedding failed for batch {batch_num}: {batch_error}",
                                extra={"model": self._model_name, "batch_size": len(batch), "attempts": attempt + 1},
                                exc_info=True
                            )
                            raise RuntimeError(
                                f"Failed to generate OpenAI embeddings for batch {batch_num}: {batch_error}"
                            ) from batch_error

            # Reconstruct full results with zeros for invalid texts
            results = []
            valid_idx = 0
            for i in range(len(texts)):
                if i in valid_indices:
                    results.append(valid_embeddings[valid_idx])
                    valid_idx += 1
                else:
                    results.append([0.0] * self._dimension)

            return results

        except Exception as e:
            logger.error(
                f"OpenAI API batch embedding failed: {e}",
                extra={"model": self._model_name, "total_texts": len(texts)},
                exc_info=True
            )
            raise RuntimeError(f"Failed to generate OpenAI batch embeddings: {e}") from e

    def get_dimension(self) -> int:
        """
        Get embedding dimension.

        Returns:
            Embedding dimension (e.g., 1536 for text-embedding-3-small)
        """
        return self._dimension

    @property
    def provider_name(self) -> str:
        """Provider name"""
        return "openai"

    @property
    def model_name(self) -> str:
        """Model name"""
        return self._model_name
