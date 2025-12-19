# backend/app/services/embeddings/openai_provider.py
"""
OpenAI embedding provider (paid API).
Uses OpenAI's embedding models via API.
"""
from typing import List
from openai import OpenAI
from app.core.embeddings.base import EmbeddingProvider
from app.utils.logging import logger


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

    # Model dimensions mapping
    DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,  # Legacy model
    }

    def __init__(self, api_key: str, model_name: str = "text-embedding-3-small"):
        """
        Initialize OpenAI embedding client.

        Args:
            api_key: OpenAI API key
            model_name: OpenAI embedding model name
                - text-embedding-3-small: 1536d, $0.02 per 1M tokens (recommended)
                - text-embedding-3-large: 3072d, $0.13 per 1M tokens (higher quality)
                - text-embedding-ada-002: 1536d, legacy model
        """
        if not api_key:
            raise ValueError("OpenAI API key is required for OpenAI embeddings")

        self._model_name = model_name
        self.client = OpenAI(api_key=api_key)

        # Get dimension from mapping
        if model_name not in self.DIMENSIONS:
            raise ValueError(f"Unknown OpenAI model: {model_name}. Supported: {list(self.DIMENSIONS.keys())}")

        self._dimension = self.DIMENSIONS[model_name]

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

        # Edge case: Handle API failures
        try:
            response = self.client.embeddings.create(
                model=self._model_name,
                input=text
            )

            # Edge case: Validate API response
            if not response or not response.data:
                raise RuntimeError("OpenAI API returned empty response")

            if len(response.data) == 0:
                raise RuntimeError("OpenAI API returned no embeddings")

            embedding = response.data[0].embedding

            # Edge case: Validate embedding dimension
            if len(embedding) != self._dimension:
                logger.warning(
                    f"OpenAI embedding dimension mismatch: expected {self._dimension}, got {len(embedding)}"
                )

            return embedding

        except Exception as e:
            logger.error(
                f"OpenAI API embedding failed: {e}",
                extra={"model": self._model_name, "text_length": len(text)},
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

                # Edge case: Handle API failures per batch
                try:
                    response = self.client.embeddings.create(
                        model=self._model_name,
                        input=batch
                    )

                    # Edge case: Validate API response
                    if not response or not response.data:
                        raise RuntimeError(f"OpenAI API returned empty response for batch {i//max_batch_size + 1}")

                    if len(response.data) != len(batch):
                        raise RuntimeError(
                            f"OpenAI API returned {len(response.data)} embeddings "
                            f"but expected {len(batch)} for batch {i//max_batch_size + 1}"
                        )

                    # Extract embeddings (response.data is sorted by input order)
                    batch_embeddings = [item.embedding for item in response.data]
                    valid_embeddings.extend(batch_embeddings)

                except Exception as batch_error:
                    logger.error(
                        f"OpenAI API batch embedding failed for batch {i//max_batch_size + 1}: {batch_error}",
                        extra={"model": self._model_name, "batch_size": len(batch)},
                        exc_info=True
                    )
                    raise RuntimeError(
                        f"Failed to generate OpenAI embeddings for batch {i//max_batch_size + 1}: {batch_error}"
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
