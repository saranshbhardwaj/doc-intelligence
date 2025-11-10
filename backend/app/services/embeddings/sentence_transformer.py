# backend/app/services/embeddings/sentence_transformer.py
"""
Sentence Transformer embedding provider (free, local).
Uses HuggingFace sentence-transformers library.
"""
from typing import List
from sentence_transformers import SentenceTransformer
from app.services.embeddings.base import EmbeddingProvider
from app.utils.logging import logger


class SentenceTransformerEmbedding(EmbeddingProvider):
    """
    Sentence Transformer embedding provider.

    Pros:
    - Free (no API costs)
    - Fast (local, no network latency)
    - Good quality for most use cases
    - Works offline

    Cons:
    - Slightly lower quality than OpenAI for some tasks
    - First run downloads model (~80MB for all-MiniLM-L6-v2)
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize Sentence Transformer model.

        Args:
            model_name: HuggingFace model name (default: all-MiniLM-L6-v2)
                - all-MiniLM-L6-v2: Fast, 384 dimensions, good quality
                - all-mpnet-base-v2: Slower, 768 dimensions, better quality
                - multi-qa-MiniLM-L6-cos-v1: Optimized for Q&A, 384 dimensions

        Raises:
            ValueError: If model_name is invalid
            RuntimeError: If model loading fails
        """
        # Edge case: Validate model_name
        if not model_name or not isinstance(model_name, str):
            raise ValueError(f"Invalid model_name: {model_name} (expected non-empty string)")

        if not model_name.strip():
            raise ValueError("model_name cannot be empty string")

        self._model_name = model_name
        logger.info(f"Loading Sentence Transformer model: {model_name}")

        # Load model (auto-downloads on first run, cached afterwards)
        # Edge case: Handle model loading failures
        try:
            self.model = SentenceTransformer(model_name)
        except Exception as e:
            logger.error(
                f"Failed to load Sentence Transformer model '{model_name}': {e}",
                exc_info=True
            )
            raise RuntimeError(
                f"Failed to load Sentence Transformer model '{model_name}'. "
                f"Ensure the model name is valid and you have internet connection for first download. "
                f"Error: {e}"
            ) from e

        # Get embedding dimension from model
        # Edge case: Handle dimension retrieval failure
        try:
            self._dimension = self.model.get_sentence_embedding_dimension()
            if not isinstance(self._dimension, int) or self._dimension <= 0:
                raise ValueError(f"Invalid embedding dimension: {self._dimension}")
        except Exception as e:
            logger.error(f"Failed to get embedding dimension: {e}", exc_info=True)
            raise RuntimeError(f"Failed to get embedding dimension from model: {e}") from e

        logger.info(f"Sentence Transformer loaded: {model_name} (dimension: {self._dimension})")

    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text to embed

        Returns:
            List of floats (embedding vector)

        Raises:
            ValueError: If text is invalid
            RuntimeError: If encoding fails
        """
        # Edge case: Validate text input
        if not isinstance(text, str):
            raise ValueError(f"text must be a string, got {type(text).__name__}")

        if not text or not text.strip():
            logger.warning("Empty text provided for embedding, returning zero vector")
            return [0.0] * self._dimension

        # Edge case: Handle encoding failures
        try:
            # encode() returns numpy array, convert to list
            embedding = self.model.encode(text, convert_to_tensor=False)

            # Edge case: Validate return type
            if not hasattr(embedding, 'tolist'):
                raise RuntimeError(f"Unexpected embedding type: {type(embedding).__name__}")

            result = embedding.tolist()

            # Edge case: Validate result is correct dimension
            if len(result) != self._dimension:
                logger.warning(
                    f"Embedding dimension mismatch: expected {self._dimension}, got {len(result)}"
                )

            return result

        except Exception as e:
            logger.error(f"Failed to encode text: {e}", exc_info=True)
            raise RuntimeError(f"Failed to generate embedding: {e}") from e

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (batched for efficiency).

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors

        Raises:
            ValueError: If texts is invalid
            RuntimeError: If encoding fails
        """
        # Edge case: Validate texts input
        if not isinstance(texts, list):
            raise ValueError(f"texts must be a list, got {type(texts).__name__}")

        if not texts:
            logger.warning("Empty texts list provided for batch embedding")
            return []

        # Edge case: Filter out empty texts and track indices
        valid_texts = []
        valid_indices = []
        for i, text in enumerate(texts):
            if isinstance(text, str) and text and text.strip():
                valid_texts.append(text)
                valid_indices.append(i)
            else:
                logger.warning(f"Skipping invalid text at index {i}: {type(text).__name__}")

        if not valid_texts:
            logger.warning("No valid texts in batch after filtering")
            return [[0.0] * self._dimension] * len(texts)

        # Edge case: Handle encoding failures
        try:
            # Batch encoding is much faster than one-by-one
            embeddings = self.model.encode(
                valid_texts,
                convert_to_tensor=False,
                show_progress_bar=len(valid_texts) > 50  # Show progress for large batches
            )

            # Edge case: Validate return type
            if not hasattr(embeddings, 'tolist'):
                raise RuntimeError(f"Unexpected embeddings type: {type(embeddings).__name__}")

            valid_results = embeddings.tolist()

            # Reconstruct full results with zeros for invalid texts
            results = []
            valid_idx = 0
            for i in range(len(texts)):
                if i in valid_indices:
                    results.append(valid_results[valid_idx])
                    valid_idx += 1
                else:
                    results.append([0.0] * self._dimension)

            return results

        except Exception as e:
            logger.error(f"Failed to encode batch: {e}", exc_info=True)
            raise RuntimeError(f"Failed to generate batch embeddings: {e}") from e

    def get_dimension(self) -> int:
        """
        Get embedding dimension.

        Returns:
            Embedding dimension (e.g., 384 for all-MiniLM-L6-v2)
        """
        return self._dimension

    @property
    def provider_name(self) -> str:
        """Provider name"""
        return "sentence-transformer"

    @property
    def model_name(self) -> str:
        """Model name"""
        return self._model_name
