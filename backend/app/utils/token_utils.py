"""Token counting and manipulation utilities.

Provides shared utilities for token operations used across the application:
- count_tokens: Count tokens in text using tiktoken
- truncate_to_token_limit: Truncate text to fit within token limit

These utilities use the cl100k_base encoding for compatibility with most models.
"""
import tiktoken
from app.utils.logging import logger

# Initialize tokenizer (using cl100k_base for compatibility with most models)
_tokenizer = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """
    Count tokens in text using tiktoken.

    Args:
        text: Text to count tokens for

    Returns:
        Number of tokens
    """
    if not text:
        return 0
    return len(_tokenizer.encode(text))


def truncate_to_token_limit(text: str, token_limit: int) -> str:
    """
    Truncate text to fit within token limit.

    Primarily used by re-ranker to ensure chunks fit cross-encoder's 512 token limit.
    Truncates from the end of the text.

    Args:
        text: Text to truncate
        token_limit: Maximum number of tokens

    Returns:
        Truncated text (or original if already within limit)
    """
    if not text:
        return text

    tokens = _tokenizer.encode(text)

    if len(tokens) <= token_limit:
        return text

    # Truncate tokens
    truncated_tokens = tokens[:token_limit]
    truncated_text = _tokenizer.decode(truncated_tokens)

    logger.debug(
        f"Truncated text: {len(tokens)} → {len(truncated_tokens)} tokens",
        extra={"original_tokens": len(tokens), "truncated_tokens": len(truncated_tokens)}
    )

    return truncated_text
