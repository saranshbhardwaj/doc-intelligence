"""Repository layer for data access.

Repositories encapsulate all database operations, providing a clean
interface between business logic and data storage.

Similar to .NET's Repository pattern with Entity Framework.

Available repositories:
- ExtractionRepository: Extraction CRUD operations
- CollectionRepository: Collection CRUD operations
- SessionRepository: Chat session operations
- DocumentRepository: Document operations
- UserRepository: User statistics and data
- JobRepository: Job tracking and progress
- WorkflowRepository: Workflow execution tracking
- RAGRepository: Chunk retrieval for RAG (semantic/keyword search)
"""
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.rag_repository import RAGRepository

__all__ = ["ExtractionRepository", "RAGRepository"]
