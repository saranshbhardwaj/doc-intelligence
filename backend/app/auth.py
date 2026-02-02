# backend/app/auth.py
"""Clerk authentication middleware and dependencies"""
from fastapi import HTTPException, Depends, Request
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
from app.config import settings
from app.db_models_users import User
from app.repositories.user_repository import UserRepository
import httpx


# Initialize Clerk client
clerk = Clerk(bearer_auth=settings.clerk_secret_key)


def _get_auth_context(request: Request) -> tuple[str, str, dict]:
    """
    Extract and verify Clerk session token from request.

    Returns:
        (user_id, org_id, payload)
    """
    # Get authorization header
    auth_header = request.headers.get("authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        print("❌ [Auth Backend] Missing or invalid authorization header")
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    try:
        # Convert FastAPI request to httpx request for Clerk SDK
        httpx_request = httpx.Request(
            method=request.method,
            url=str(request.url),
            headers=dict(request.headers)
        )

        # Authenticate the request with Clerk
        # Empty options accepts session tokens by default (not OAuth tokens)
        from clerk_backend_api.security.types import AuthenticateRequestOptions
        request_state = clerk.authenticate_request(
            httpx_request,
            AuthenticateRequestOptions()
        )

        if not request_state.is_signed_in:
            print(f"❌ [Auth Backend] User is not signed in")
            raise HTTPException(status_code=401, detail="Not signed in")

        payload = request_state.payload or {}

        # Extract user_id from the token payload
        # The user ID is in the 'sub' field of the JWT payload
        user_id = payload.get('sub')

        # Extract org_id from the token payload (Clerk Organizations)
        # Clerk uses org_id in JWT for active organization
        org_id = payload.get('org_id') or payload.get('orgId')

        if not user_id:
            print(f"❌ [Auth Backend] Could not extract user_id from token payload: {payload}")
            raise HTTPException(status_code=401, detail="Could not extract user_id from token")

        if not org_id:
            print(f"❌ [Auth Backend] Could not extract org_id from token payload: {payload}")
            raise HTTPException(status_code=401, detail="Could not extract org_id from token")

        return user_id, org_id, payload

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ [Auth Backend] Token verification failed: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Invalid session token: {str(e)}")


def get_current_user_id(request: Request) -> str:
    """
    Extract and verify Clerk session token from request.
    Returns the Clerk user ID.
    """
    user_id, _org_id, _payload = _get_auth_context(request)
    return user_id


def get_current_org_role(request: Request) -> str:
    """Extract org_role from Clerk token payload."""
    _user_id, _org_id, payload = _get_auth_context(request)
    org_role = payload.get("org_role") or payload.get("orgRole")
    if not org_role:
        raise HTTPException(status_code=403, detail="Missing org_role")
    return str(org_role)


def is_admin_role(role: str) -> bool:
    """Return True if role is admin/owner."""
    return role.lower() in {"admin", "owner"}


def require_org_role(allowed_roles: list[str]):
    """Dependency to enforce allowed org roles."""
    allowed = {r.lower() for r in allowed_roles}

    def _dep(request: Request) -> str:
        role = get_current_org_role(request).lower()
        if role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient org_role")
        return role

    return _dep


def get_current_user(request: Request) -> User:
    """
    Get or create user from database using repository pattern.
    If user doesn't exist (first login), create them.
    Handles race conditions gracefully.
    """
    # First authenticate the user
    user_id, org_id, _payload = _get_auth_context(request)

    # Use repository for all database operations
    user_repo = UserRepository()

    # Fetch user details from Clerk for potential creation
    clerk_user = clerk.users.get(user_id=user_id)
    email = clerk_user.email_addresses[0].email_address if clerk_user.email_addresses else f"{user_id}@unknown.com"

    # Get existing user or create new one
    user = user_repo.get_or_create_user(
        user_id=user_id,
        org_id=org_id,
        email=email,
        tier="free",
        pages_limit=100
    )

    if not user:
        # This shouldn't happen - log and raise error
        print(f"❌ [Auth Backend] Failed to get or create user: {user_id}")
        raise HTTPException(status_code=500, detail="Failed to authenticate user")

    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency that requires admin tier"""
    if user.tier != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
