# backend/app/services/embeddings/factory.py
"""
Factory for creating embedding providers based on configuration.
Allows easy switching between embedding models via config.
"""
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.sentence_transformer import SentenceTransformerEmbedding
from app.services.embeddings.openai_provider import OpenAIEmbedding
from app.config import Settings
from app.utils.logging import logger


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """
    Create embedding provider based on configuration.

    Args:
        settings: Application settings

    Returns:
        EmbeddingProvider instance

    Raises:
        ValueError: If provider is not supported or configuration is invalid
    """
    # Edge case: Validate settings object
    if not settings:
        raise ValueError("settings parameter is required")

    # Edge case: Validate embedding_provider attribute exists
    if not hasattr(settings, 'embedding_provider'):
        raise ValueError("settings object missing 'embedding_provider' attribute")

    provider_raw = settings.embedding_provider

    # Edge case: Validate provider is not None or empty
    if not provider_raw or not isinstance(provider_raw, str):
        raise ValueError(
            f"Invalid embedding_provider: {provider_raw} (expected non-empty string). "
            f"Set EMBEDDING_PROVIDER in your .env file to 'sentence-transformer' or 'openai'."
        )

    provider = provider_raw.lower().strip()

    if not provider:
        raise ValueError(
            "embedding_provider cannot be empty. "
            "Set EMBEDDING_PROVIDER in your .env file to 'sentence-transformer' or 'openai'."
        )

    logger.info(f"Initializing embedding provider: {provider}")

    if provider == "sentence-transformer":
        # Edge case: Validate model name attribute
        if not hasattr(settings, 'sentence_transformer_model'):
            raise ValueError("settings object missing 'sentence_transformer_model' attribute")

        model_name = settings.sentence_transformer_model
        if not model_name or not isinstance(model_name, str):
            raise ValueError(
                f"Invalid sentence_transformer_model: {model_name} (expected non-empty string). "
                f"Set SENTENCE_TRANSFORMER_MODEL in your .env file."
            )

        return SentenceTransformerEmbedding(model_name=model_name)

    elif provider == "openai":
        # Edge case: Validate API key attribute
        if not hasattr(settings, 'openai_api_key'):
            raise ValueError("settings object missing 'openai_api_key' attribute")

        if not settings.openai_api_key:
            raise ValueError(
                "OpenAI API key is required when using OpenAI embeddings. "
                "Set OPENAI_API_KEY in your .env file."
            )

        # Edge case: Validate model name attribute
        if not hasattr(settings, 'openai_embedding_model'):
            raise ValueError("settings object missing 'openai_embedding_model' attribute")

        model_name = settings.openai_embedding_model
        if not model_name or not isinstance(model_name, str):
            raise ValueError(
                f"Invalid openai_embedding_model: {model_name} (expected non-empty string). "
                f"Set OPENAI_EMBEDDING_MODEL in your .env file."
            )

        return OpenAIEmbedding(
            api_key=settings.openai_api_key,
            model_name=model_name
        )

    else:
        raise ValueError(
            f"Unknown embedding provider: '{provider}'. "
            f"Supported providers: sentence-transformer, openai"
        )


# Global singleton instance (initialized lazily on first use)
_embedding_provider: EmbeddingProvider | None = None


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    """
    Get or create the global embedding provider singleton.

    This ensures we only load the embedding model once (expensive operation).

    Args:
        settings: Application settings (required on first call)

    Returns:
        EmbeddingProvider instance

    Raises:
        ValueError: If settings are invalid
        RuntimeError: If provider initialization fails
    """
    global _embedding_provider

    if _embedding_provider is None:
        # Edge case: Get default settings if none provided
        if settings is None:
            try:
                from app.config import settings as default_settings
                settings = default_settings
            except Exception as e:
                logger.error(f"Failed to load default settings: {e}", exc_info=True)
                raise RuntimeError(f"Failed to load default settings for embedding provider: {e}") from e

        # Edge case: Validate settings loaded successfully
        if settings is None:
            raise ValueError("Failed to load settings - settings object is None")

        # Edge case: Handle provider creation failures
        try:
            _embedding_provider = create_embedding_provider(settings)
        except Exception as e:
            logger.error(f"Failed to create embedding provider: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize embedding provider: {e}") from e

        # Edge case: Validate provider was created successfully
        if _embedding_provider is None:
            raise RuntimeError("Embedding provider creation returned None")

        logger.info(
            f"Embedding provider initialized: {_embedding_provider.provider_name} "
            f"({_embedding_provider.model_name}, {_embedding_provider.get_dimension()}d)"
        )

    return _embedding_provider
