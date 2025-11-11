"""
Centralized ID generation utilities.

All IDs in the system should use these functions for consistency.
"""
import uuid


def generate_id() -> str:
    """
    Generate a unique ID for database records.

    Returns:
        36-character UUID string (e.g., "550e8400-e29b-41d4-a716-446655440000")
    """
    return str(uuid.uuid4())


def generate_short_id() -> str:
    """
    Generate a shorter unique ID (first 8 characters of UUID).

    Useful for user-facing IDs or when space is limited.
    Note: Collision probability is higher than full UUID.

    Returns:
        8-character hex string (e.g., "550e8400")
    """
    return str(uuid.uuid4())[:8]


def generate_request_id() -> str:
    """
    Generate a unique request/trace ID for logging and debugging.

    Returns:
        36-character UUID string
    """
    return str(uuid.uuid4())
