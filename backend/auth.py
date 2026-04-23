"""
FastAPI dependency for Supabase JWT verification.

Supabase signs JWTs with HS256 using SUPABASE_JWT_SECRET.
We verify locally for performance — no extra network round-trip.

Usage in endpoint:
    @router.get("/protected")
    async def protected(user: dict = Depends(get_current_user)):
        return {"uid": user["sub"]}
"""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import get_settings

_bearer = HTTPBearer(auto_error=True)


def _verify_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict:
    """Return decoded JWT payload. Raises 401 if invalid."""
    return _verify_token(credentials.credentials)


def get_user_id(user: Annotated[dict, Depends(get_current_user)]) -> str:
    """Convenience: extract sub (Supabase user UUID) from JWT."""
    uid = user.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Missing user id in token")
    return uid


# Type alias for cleaner endpoint signatures
CurrentUser = Annotated[dict, Depends(get_current_user)]
UserId = Annotated[str, Depends(get_user_id)]
