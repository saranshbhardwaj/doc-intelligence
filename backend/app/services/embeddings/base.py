# backend/app/services/embeddings/base.py
"""
Base abstract class for embedding providers.
This allows easy switching between different embedding models (local, OpenAI, etc.)
"""
from abc import ABC, abstractmethod
from typing import List


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers"""

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text string.

        Args:
            text: Input text to embed

        Returns:
            List of floats representing the embedding vector
        """
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (batch processing for efficiency).

        Args:
            texts: List of input texts to embed

        Returns:
            List of embedding vectors (one per input text)
        """
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """
        Get the dimension of the embedding vectors.

        Returns:
            Integer dimension (e.g., 384, 768, 1536)
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Name of the embedding provider (e.g., "sentence-transformer", "openai")

        Returns:
            String name of provider
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """
        Name of the specific model being used

        Returns:
            String model name (e.g., "all-MiniLM-L6-v2", "text-embedding-3-small")
        """
        pass
