"""
FastAPI dependency for Supabase JWT verification.

Verification is delegated to Supabase's API (get_user) rather than done
locally with a hardcoded algorithm. This handles HS256 (email OTP),
ES256 (Google OAuth), and any future Supabase signing changes automatically.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.services.supabase_client import admin_client

_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict:
    """Verify token via Supabase and return the user dict. Raises 401 if invalid."""
    token = credentials.credentials
    try:
        client = await admin_client()
        resp = await client.auth.get_user(token)
        if not resp or not resp.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = resp.user
        return {"sub": user.id, "email": user.email, "user": user}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_user_id(user: Annotated[dict, Depends(get_current_user)]) -> str:
    """Convenience: extract sub (Supabase user UUID) from verified user."""
    uid = user.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Missing user id in token")
    return uid


# Type aliases for cleaner endpoint signatures
CurrentUser = Annotated[dict, Depends(get_current_user)]
UserId = Annotated[str, Depends(get_user_id)]
