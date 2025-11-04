# backend/app/auth.py
"""Clerk authentication middleware and dependencies"""
from fastapi import HTTPException, Depends, Request
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
from app.config import settings
from app.database import get_db
from app.db_models_users import User
from sqlalchemy.orm import Session
from datetime import datetime
import httpx


# Initialize Clerk client
clerk = Clerk(bearer_auth=settings.clerk_secret_key)


def get_current_user_id(request: Request) -> str:
    """
    Extract and verify Clerk session token from request.
    Returns the Clerk user ID.
    """
    # Get authorization header
    auth_header = request.headers.get("authorization")
    print(f"🔐 [Auth Backend] Authorization header: {auth_header[:50] if auth_header else 'None'}...")

    if not auth_header or not auth_header.startswith("Bearer "):
        print("❌ [Auth Backend] Missing or invalid authorization header")
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    try:
        # Convert FastAPI request to httpx request for Clerk SDK
        print("🔐 [Auth Backend] Verifying request with Clerk...")
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

        # Extract user_id from the token payload
        # The user ID is in the 'sub' field of the JWT payload
        user_id = request_state.payload.get('sub') if request_state.payload else None

        if not user_id:
            print(f"❌ [Auth Backend] Could not extract user_id from token payload: {request_state.payload}")
            raise HTTPException(status_code=401, detail="Could not extract user_id from token")

        print(f"✅ [Auth Backend] Token verified! User ID: {user_id}")
        return user_id

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ [Auth Backend] Token verification failed: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Invalid session token: {str(e)}")


def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """
    Get or create user from database.
    If user doesn't exist (first login), create them.
    """
    # First authenticate the user
    user_id = get_current_user_id(request)

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        # First time login - fetch user details from Clerk and create in our DB
        clerk_user = clerk.users.get(user_id=user_id)

        user = User(
            id=user_id,
            email=clerk_user.email_addresses[0].email_address if clerk_user.email_addresses else f"{user_id}@unknown.com",
            tier="free",
            pages_limit=100,
            total_pages_processed=0,
            pages_this_month=0
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Update last login
        user.last_login = datetime.now()
        db.commit()

    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency that requires admin tier"""
    if user.tier != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
