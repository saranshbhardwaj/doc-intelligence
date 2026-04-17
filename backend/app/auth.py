# backend/app/auth.py
"""WorkOS AuthKit authentication middleware and dependencies"""
import logging
from fastapi import HTTPException, Depends, Request
import jwt
from jwt import PyJWKClient
from app.config import settings
from app.db_models_users import User
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# Custom claim namespace configured in WorkOS JWT template (Authentication → Sessions → Custom claims)
_CLAIM_PREFIX = "urn:myapp:"

def _claim(name: str) -> str:
    """Return the fully-namespaced claim key, e.g. 'org_id' → 'urn:myapp:org_id'."""
    return f"{_CLAIM_PREFIX}{name}"


# Initialize JWKS client once at module load.
# PyJWKClient caches the public keys internally and re-fetches when a key is not found.
# Falls back gracefully (503) if WORKOS_CLIENT_ID is not yet configured.
_jwks_client: PyJWKClient | None = None
if settings.workos_client_id:
    _jwks_client = PyJWKClient(
        f"https://api.workos.com/sso/jwks/{settings.workos_client_id}"
    )


def _verify_token(token: str) -> dict:
    """
    Verify a WorkOS JWT and return the decoded payload.
    Raises HTTPException on failure.
    Can be called directly with a raw token string (used by SSE endpoint).
    """
    if not _jwks_client:
        logger.error("[AUTH] JWKS client not initialized — missing WORKOS_CLIENT_ID")
        raise HTTPException(status_code=503, detail="Auth not configured (missing WORKOS_CLIENT_ID)")
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(token, signing_key.key, algorithms=["RS256"])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("[AUTH] Token expired")
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"[AUTH] Invalid token: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        logger.error(f"[AUTH] Token verification failed: {e}")
        raise HTTPException(status_code=401, detail=f"Token verification failed: {str(e)}")


def _get_auth_context(request: Request) -> tuple[str, str, dict]:
    """
    Extract and verify WorkOS JWT from Authorization header.

    Returns:
        (user_id, org_id, payload)
    """
    auth_header = request.headers.get("authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = auth_header.split(" ", 1)[1]
    payload = _verify_token(token)

    user_id = payload.get("sub")           # standard JWT claim — no namespace
    org_id = payload.get(_claim("org_id"))

    if not user_id:
        raise HTTPException(status_code=401, detail="Could not extract user_id from token")

    if not org_id:
        raise HTTPException(status_code=401, detail="Could not extract org_id from token")

    return user_id, org_id, payload


def get_current_user_id(request: Request) -> str:
    """Returns the WorkOS user ID from the request token."""
    user_id, _org_id, _payload = _get_auth_context(request)
    return user_id


def get_current_org_role(request: Request) -> str:
    """Extract org_role from WorkOS token payload."""
    _user_id, _org_id, payload = _get_auth_context(request)
    org_role = payload.get(_claim("org_role"))
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
    Email is extracted directly from the WorkOS JWT claim (configure in WorkOS dashboard
    under JWT template to include the 'email' claim).
    """
    user_id, org_id, payload = _get_auth_context(request)

    # Email comes directly from JWT claim — no Clerk API call needed
    email = payload.get(_claim("email")) or f"{user_id}@unknown.com"

    user_repo = UserRepository()
    user = user_repo.get_or_create_user(
        user_id=user_id,
        org_id=org_id,
        email=email,
        tier="free",
        pages_limit=100
    )

    if not user:
        raise HTTPException(status_code=500, detail="Failed to authenticate user")

    if getattr(user, "status", "active") != "active":
        raise HTTPException(status_code=403, detail="access_pending")

    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency that requires admin tier"""
    if user.tier != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_vertical(vertical_slug: str):
    """Dependency factory that gates access to a specific vertical.

    Usage:
        router = APIRouter(dependencies=[Depends(require_vertical("private_equity"))])
    """
    def _dep(user: User = Depends(get_current_user)) -> User:
        allowed = user.allowed_verticals or []
        if user.tier == "admin":
            return user
        if vertical_slug not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"no_access_{vertical_slug}"
            )
        return user
    return _dep
