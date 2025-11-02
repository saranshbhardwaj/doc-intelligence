"""Repository layer for data access.

Repositories encapsulate all database operations, providing a clean
interface between business logic and data storage.

Similar to .NET's Repository pattern with Entity Framework.
"""
from app.repositories.extraction_repository import ExtractionRepository

__all__ = ["ExtractionRepository"]
