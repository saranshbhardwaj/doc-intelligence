# backend/app/api/chat/collections.py
"""Collection management endpoints for Chat Mode."""

from typing import Optional
from fastapi import APIRouter, Form, HTTPException, Depends, Query

from app.auth import get_current_user
from app.db_models_users import User
from app.repositories.collection_repository import CollectionRepository
from app.utils.logging import logger

router = APIRouter()


@router.post("/collections")
async def create_collection(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    user: User = Depends(get_current_user)
):
    """
    Create a new collection for multi-document chat.

    Args:
        name: Collection name (1-100 chars)
        description: Optional description (max 500 chars)
        user: Current user (from auth)

    Returns:
        Collection details

    Raises:
        HTTPException 400: Invalid input (empty name, too long, etc.)
        HTTPException 500: Database error
    """
    # Edge case: Validate name
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Collection name cannot be empty")

    name = name.strip()
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Collection name must be 100 characters or less")

    # Edge case: Validate description length
    if description and len(description) > 500:
        raise HTTPException(status_code=400, detail="Description must be 500 characters or less")

    # Use repository for database operations
    collection_repo = CollectionRepository()
    collection = collection_repo.create_collection(
        user_id=user.id,
        name=name,
        description=description.strip() if description else None
    )

    if not collection:
        raise HTTPException(status_code=500, detail="Failed to create collection")

    logger.info(
        f"Created collection",
        extra={"user_id": user.id, "collection_id": collection.id, "collection_name": name}
    )

    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "document_count": collection.document_count,
        "total_chunks": collection.total_chunks,
        "created_at": collection.created_at.isoformat() if collection.created_at else None,
    }


@router.get("/collections")
async def list_collections(
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    List all collections for the current user.

    Args:
        user: Current user
        limit: Max results (1-100, default: 50)
        offset: Pagination offset (>=0, default: 0)

    Returns:
        List of collections with pagination metadata
    """
    collection_repo = CollectionRepository()
    collections, total = collection_repo.list_collections(
        user_id=user.id,
        limit=limit,
        offset=offset
    )

    return {
        "collections": [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "document_count": c.document_count,
                "total_chunks": c.total_chunks,
                "embedding_model": c.embedding_model,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in collections
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/collections/{collection_id}")
async def get_collection(
    collection_id: str,
    user: User = Depends(get_current_user)
):
    """
    Get collection details including documents.

    Args:
        collection_id: Collection ID (UUID format)
        user: Current user

    Returns:
        Collection with documents list

    Raises:
        HTTPException 404: Collection not found or access denied
    """
    collection_repo = CollectionRepository()

    # Get collection (with ownership check)
    collection = collection_repo.get_collection(collection_id, user.id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Get documents in collection
    documents = collection_repo.list_documents(collection_id)

    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "document_count": collection.document_count,
        "total_chunks": collection.total_chunks,
        "embedding_model": collection.embedding_model,
        "embedding_dimension": collection.embedding_dimension,
        "created_at": collection.created_at.isoformat() if collection.created_at else None,
        "updated_at": collection.updated_at.isoformat() if collection.updated_at else None,
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "page_count": d.page_count,
                "chunk_count": d.chunk_count,
                "has_embeddings": d.chunk_count > 0 and d.status == "completed",
                "status": d.status,
                "error_message": d.error_message,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "completed_at": d.completed_at.isoformat() if d.completed_at else None,
            }
            for d in documents
        ]
    }


@router.delete("/collections/{collection_id}")
async def delete_collection(
    collection_id: str,
    user: User = Depends(get_current_user)
):
    """
    Delete a collection (cascades to documents, chunks, sessions).

    Args:
        collection_id: Collection ID
        user: Current user

    Returns:
        Success message

    Raises:
        HTTPException 404: Collection not found or access denied
        HTTPException 409: Collection has active indexing jobs (future enhancement)
    """
    collection_repo = CollectionRepository()

    # Edge case: Check if collection exists before attempting delete
    collection = collection_repo.get_collection(collection_id, user.id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    success = collection_repo.delete_collection(collection_id, user.id)
    if not success:
        # Should not happen if the above check passed, but defensive
        raise HTTPException(status_code=500, detail="Failed to delete collection")

    logger.info(
        f"Deleted collection",
        extra={
            "user_id": user.id,
            "collection_id": collection_id,
            "collection_name": collection.name,
            "document_count": collection.document_count
        }
    )

    return {"success": True, "message": "Collection deleted"}
