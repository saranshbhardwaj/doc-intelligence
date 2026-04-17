# backend/app/api/users.py
"""User profile and extraction history endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from workos import WorkOSClient
from app.auth import get_current_user, get_current_org_role, is_admin_role, _verify_token, _claim
from app.db_models_users import User
from app.repositories.extraction_repository import ExtractionRepository
from app.services.beta_limits import get_usage_snapshot
from app.utils.logging import logger
from pathlib import Path
from app.config import settings

router = APIRouter()

# Initialize WorkOS client for org management
_workos = None
if settings.workos_api_key and settings.workos_client_id:
    _workos = WorkOSClient(api_key=settings.workos_api_key, client_id=settings.workos_client_id)


def _extract_first_claim(payload: dict, names: list[str], default: str = "") -> str:
    """Return first non-empty claim value from namespaced or standard claim keys."""
    for name in names:
        for key in (_claim(name), name):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return default


def _build_default_org_name(payload: dict) -> str:
    """Generate a safe default workspace/org name for first-time signup."""
    full_name = _extract_first_claim(payload, ["full_name", "name"])
    if full_name:
        return full_name[:80]

    email = _extract_first_claim(payload, ["email"])
    if email and "@" in email:
        local_part = email.split("@", 1)[0].strip()
        if local_part:
            return f"{local_part[:50]}'s Workspace"

    return "My Workspace"


def _find_existing_membership_org_id(user_id: str) -> str | None:
    """Return existing org_id for this user from WorkOS memberships, if any."""
    memberships = _workos.user_management.list_organization_memberships(
        user_id=user_id,
        limit=100,
    )
    data = list(getattr(memberships, "data", []) or [])
    if not data:
        return None

    # Prefer active memberships, otherwise fall back to the first available.
    active = [m for m in data if getattr(m, "status", "") == "active"]
    selected = active[0] if active else data[0]
    return getattr(selected, "organization_id", None)


def _resolve_initial_role_slug(organization_id: str) -> str | None:
    """Pick a role slug for first membership if roles are configured."""
    preferred = ("owner", "admin", "member")
    roles = _workos.organizations.list_organization_roles(organization_id).data
    slugs = {getattr(r, "slug", "") for r in roles}
    for slug in preferred:
        if slug in slugs:
            return slug
    return None


def _org_external_id_for_user(user_id: str) -> str:
    """Stable external ID to ensure one default org per user."""
    return f"default-org-for:{user_id}"


def _get_org_by_external_id(external_id: str):
    """Return org by external_id, or None if not found."""
    try:
        return _workos.organizations.get_organization_by_external_id(external_id)
    except Exception:
        return None


def _membership_exists(user_id: str, organization_id: str) -> bool:
    """Check whether the user is already a member of the org."""
    memberships = _workos.user_management.list_organization_memberships(
        user_id=user_id,
        organization_id=organization_id,
        limit=1,
    )
    return bool(getattr(memberships, "data", []))


@router.get("/api/users/me")
def get_current_user_info(user: User = Depends(get_current_user)):
    """Get current user's profile and usage stats"""
    # For free tier, use total pages (one-time limit)
    # For paid tiers, use monthly pages (recurring limit)
    if user.tier == "free":
        pages_used = user.total_pages_processed
        pages_remaining = max(0, user.pages_limit - user.total_pages_processed)
    else:
        pages_used = user.pages_this_month
        pages_remaining = max(0, user.pages_limit - user.pages_this_month)

    percentage_used = (pages_used / user.pages_limit * 100) if user.pages_limit > 0 else 0
    limits = get_usage_snapshot(user)

    return {
        "id": user.id,
        "email": user.email,
        "tier": user.tier,
        "allowed_verticals": user.allowed_verticals or ["real_estate"],
        "usage": {
            "pages_used": pages_used,
            "pages_remaining": pages_remaining,
            "pages_limit": user.pages_limit,
            "total_pages_processed": user.total_pages_processed,
            "pages_this_month": user.pages_this_month,
            "percentage_used": round(percentage_used, 1)
        },
        "limits": limits,
        "subscription": {
            "status": user.subscription_status,
            "billing_period_end": user.billing_period_end.isoformat() if user.billing_period_end else None
        }
    }


@router.get("/api/users/me/extractions")
def get_user_extractions(
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100, description="Number of extractions to return"),
    offset: int = Query(0, ge=0, description="Number of extractions to skip"),
    status: str = Query(None, description="Filter by status (completed, processing, failed)")
):
    """Get user's extraction history with pagination and filtering

    Args:
        limit: Maximum number of results (1-100, default 50)
        offset: Number of results to skip for pagination
        status: Optional status filter

    Returns:
        extractions: List of extraction records
        total: Total count of extractions matching filters
        limit: Applied limit
        offset: Applied offset
    """
    extraction_repo = ExtractionRepository()
    extractions, total = extraction_repo.list_user_extractions(
        user_id=user.id,
        org_id=user.org_id,
        limit=limit,
        offset=offset,
        status=status
    )

    return {
        "extractions": [
            {
                "id": e.id,
                "filename": e.filename,
                "page_count": e.page_count,
                "status": e.status,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                "pdf_type": e.pdf_type,
                "parser_used": e.parser_used,
                "cost_usd": e.cost_usd,
                "processing_time_ms": e.processing_time_ms,
                "error_message": e.error_message,
                "from_cache": e.from_cache,
                "context": e.context  # User-provided context
            }
            for e in extractions
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + len(extractions)) < total
    }


@router.delete("/api/extractions/{extraction_id}")
def delete_extraction(
    extraction_id: str,
    user: User = Depends(get_current_user),
    request: Request = None
):
    """Delete an extraction and its associated files

    Requires authentication - users can only delete their own extractions.

    Args:
        extraction_id: ID of the extraction to delete

    Returns:
        success: Boolean indicating success
        message: Confirmation message
    """
    extraction_repo = ExtractionRepository()

    # Get extraction (for filename and verification)
    extraction = extraction_repo.get_extraction(extraction_id, user.org_id)

    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")

    # Verify ownership
    if extraction.user_id != user.id:
        role = get_current_org_role(request)
        if not is_admin_role(role):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to delete this extraction"
            )

    filename = extraction.filename  # Save before deletion

    # Delete associated files (raw text, parsed result, etc.)
    try:
        # Define file patterns to delete
        file_patterns = [
            settings.raw_dir / f"*_{extraction_id[:8]}.txt",
            settings.parsed_dir / f"*_{extraction_id[:8]}.json",
            settings.raw_llm_dir / f"*_{extraction_id[:8]}.json",
        ]

        files_deleted = 0
        for pattern in file_patterns:
            for file_path in Path(pattern.parent).glob(pattern.name):
                try:
                    file_path.unlink()
                    files_deleted += 1
                    logger.info(f"Deleted file: {file_path}", extra={
                        "extraction_id": extraction_id,
                        "user_id": user.id
                    })
                except Exception as e:
                    logger.warning(f"Failed to delete file {file_path}: {e}", extra={
                        "extraction_id": extraction_id
                    })

        logger.info(f"Deleted {files_deleted} files for extraction {extraction_id}", extra={
            "extraction_id": extraction_id,
            "user_id": user.id
        })

    except Exception as e:
        logger.error(f"Error deleting files: {e}", extra={
            "extraction_id": extraction_id,
            "user_id": user.id
        }, exc_info=True)  # Include full stack trace
        # Continue with DB deletion even if file deletion fails

    # Delete from database using repository
    success = extraction_repo.delete_extraction(extraction_id, user.id, user.org_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete extraction from database")

    logger.info("Extraction deleted successfully", extra={
        "extraction_id": extraction_id,
        "user_id": user.id,
        "extraction_filename": filename
    })

    return {
        "success": True,
        "message": f"Extraction '{filename}' deleted successfully"
    }


@router.post("/api/users/provision-org")
def provision_org(request: Request):
    """
    Auto-create a WorkOS organization for a new user who has no org yet.
    Called by frontend when JWT is valid but contains no org_id.
    After this endpoint succeeds, user must re-authenticate to get a new JWT with org_id.

    Returns:
        org_id: ID of the newly created organization
        org_name: Name of the organization
        already_exists: True if user already has an org (idempotent)
    """
    if not _workos:
        raise HTTPException(status_code=503, detail="WorkOS not configured (missing API key or client ID)")

    # Extract and verify token without requiring org_id
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    try:
        payload = _verify_token(auth_header.split(" ", 1)[1])
    except HTTPException:
        raise

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Could not extract user_id from token")

    # If user already has an org, return it (idempotent)
    existing_org_id = payload.get(_claim("org_id"))
    if existing_org_id:
        logger.info(f"User {user_id} already has org {existing_org_id}", extra={"user_id": user_id})
        return {"org_id": existing_org_id, "already_exists": True}

    # Fast idempotency path: if token is stale but user already has a membership, use it.
    try:
        membership_org_id = _find_existing_membership_org_id(user_id)
        if membership_org_id:
            logger.info(
                f"User {user_id} already has WorkOS membership in {membership_org_id}",
                extra={"user_id": user_id, "org_id": membership_org_id},
            )
            return {"org_id": membership_org_id, "already_exists": True}
    except Exception as e:
        logger.warning(
            f"Failed membership lookup for user {user_id}: {e}",
            extra={"user_id": user_id},
        )

    org_name = _build_default_org_name(payload)
    external_id = _org_external_id_for_user(user_id)
    created_org_id = None

    try:
        # 1. Reuse existing external-id org if present (strong dedupe for same user).
        org = _get_org_by_external_id(external_id)
        if org:
            logger.info(
                f"Found existing external-id org {org.id} for user {user_id}",
                extra={"user_id": user_id, "org_id": org.id},
            )
        else:
            # Create organization with idempotency + external_id.
            org = _workos.organizations.create_organization(
                name=org_name,
                idempotency_key=f"provision-org:{user_id}",
                external_id=external_id,
            )
            created_org_id = org.id
            logger.info(f"Created org {org.id} for user {user_id}", extra={"user_id": user_id, "org_id": org.id})

        # 2. Add user as member (prefer owner/admin/member if roles exist).
        if _membership_exists(user_id=user_id, organization_id=org.id):
            logger.info(
                f"User {user_id} already has membership in org {org.id}",
                extra={"user_id": user_id, "org_id": org.id},
            )
            return {"org_id": org.id, "org_name": org.name, "already_exists": True}

        role_slug = None
        try:
            role_slug = _resolve_initial_role_slug(org.id)
        except Exception as role_err:
            logger.warning(
                f"Could not resolve initial role for org {org.id}: {role_err}",
                extra={"user_id": user_id, "org_id": org.id},
            )

        membership_kwargs = {"user_id": user_id, "organization_id": org.id}
        if role_slug:
            membership_kwargs["role_slug"] = role_slug

        _workos.user_management.create_organization_membership(**membership_kwargs)
        logger.info(f"Added user {user_id} to org {org.id}", extra={"user_id": user_id, "org_id": org.id})

        return {"org_id": org.id, "org_name": org.name, "role_slug": role_slug}

    except Exception as e:
        # Best-effort rollback of partial org creation if membership failed.
        if created_org_id:
            try:
                memberships = _workos.user_management.list_organization_memberships(
                    organization_id=created_org_id,
                    limit=1,
                )
                has_members = bool(getattr(memberships, "data", []))
                if not has_members:
                    _workos.organizations.delete_organization(created_org_id)
                    logger.warning(
                        f"Rolled back orphan org {created_org_id} after provisioning failure",
                        extra={"user_id": user_id, "org_id": created_org_id},
                    )
            except Exception as rollback_err:
                logger.warning(
                    f"Failed rollback for org {created_org_id}: {rollback_err}",
                    extra={"user_id": user_id, "org_id": created_org_id},
                )

        logger.error(f"Failed to provision org for user {user_id}: {e}", extra={"user_id": user_id}, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set up workspace: {str(e)}")
