"""
Gmail OAuth 2.0 server-side flow + sync endpoints.

Endpoints:
  GET  /gmail/connect   — redirect user to Google OAuth consent screen
  GET  /gmail/callback  — exchange code for tokens, store encrypted, redirect to frontend
  POST /gmail/sync      — trigger incremental Gmail sync for authenticated user
  GET  /gmail/status    — check if Gmail is connected for current user

OAuth notes:
  - access_type=offline + prompt=consent ensures refresh token is always issued
  - PKCE not required for server-side flow (client_secret present)
  - Redirect URI must be registered in Google Cloud Console
"""

import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel

from backend.auth import UserId
from backend.config import get_settings
from backend.services.background_tasks import run_gmail_sync
from backend.services.gmail_service import (
    GMAIL_SCOPES,
    fetch_statement_attachments,
    store_gmail_tokens,
    update_last_synced,
)
from backend.services.supabase_client import admin_client

router = APIRouter(prefix="/gmail", tags=["gmail"])

# In-memory state store (use Redis in production)
_oauth_states: dict[str, str] = {}  # state -> user_id


def _build_flow() -> Flow:
    settings = get_settings()
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.oauth_redirect_url],
            }
        },
        scopes=GMAIL_SCOPES,
        redirect_uri=settings.oauth_redirect_url,
    )


@router.get("/connect")
async def gmail_connect(user_id: UserId):
    """
    Start Gmail OAuth flow. Returns redirect URL for the frontend to navigate to.

    Frontend should open this URL (new tab or redirect).
    """
    flow = _build_flow()
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = user_id  # tie state to authenticated user

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        include_granted_scopes="false",
    )
    return {"auth_url": auth_url}


@router.get("/callback")
async def gmail_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: Optional[str] = Query(None),
):
    """
    Handle Google OAuth callback. Exchanges code for tokens, stores encrypted.
    Redirects to Streamlit frontend with success/error flag.
    """
    if error:
        return RedirectResponse(url=f"http://localhost:8501?gmail_error={error}")

    user_id = _oauth_states.pop(state, None)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    flow = _build_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Get Gmail user info
    from googleapiclient.discovery import build as gbuild
    service = gbuild("oauth2", "v2", credentials=creds)
    user_info = service.userinfo().get().execute()
    gmail_user_id = user_info.get("id", user_info.get("email", "unknown"))
    scope = " ".join(GMAIL_SCOPES)

    await store_gmail_tokens(
        user_id=user_id,
        gmail_user_id=gmail_user_id,
        credentials=creds,
        scope=scope,
    )

    # Clean success page that closes itself
    html = """
    <html><body>
    <h3>✅ Gmail connected successfully!</h3>
    <p>You can close this tab and return to Money Clarity.</p>
    <script>
      setTimeout(() => {
        window.opener && window.opener.postMessage({type: 'gmail_connected'}, '*');
        window.close();
      }, 1500);
    </script>
    </body></html>
    """
    return HTMLResponse(content=html)


@router.get("/status")
async def gmail_status(user_id: UserId):
    """Check if Gmail is connected for the current user."""
    client = await admin_client()
    result = (
        await client.table("gmail_accounts")
        .select("gmail_user_id, last_synced_at, scope")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        return {"connected": False}
    return {
        "connected": True,
        "gmail_user_id": result.data["gmail_user_id"],
        "last_synced_at": result.data["last_synced_at"],
    }


class SyncRequest(BaseModel):
    since: Optional[str] = None  # ISO date string, e.g. "2024-01-01"


@router.post("/sync")
async def gmail_sync(
    user_id: UserId,
    body: SyncRequest = SyncRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Trigger Gmail sync for authenticated user.

    For MVP, sync runs in background and returns immediately.
    Poll /gmail/status for last_synced_at to confirm completion.

    Body (optional):
      {"since": "2024-01-01"}  -- only fetch emails after this date
    """
    since: Optional[datetime] = None
    if body.since:
        try:
            since = datetime.fromisoformat(body.since).replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'since' date format. Use ISO format.")

    # Verify Gmail is connected
    client = await admin_client()
    result = (
        await client.table("gmail_accounts")
        .select("last_synced_at")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=400, detail="Gmail not connected. Call /gmail/connect first.")

    # For truly async background: uncomment below and return accepted status
    # background_tasks.add_task(run_gmail_sync, user_id, since)
    # return {"status": "sync_started", "message": "Check /gmail/status for completion"}

    # MVP: run synchronously and return result (simpler for frontend)
    sync_result = await run_gmail_sync(user_id, since=since)
    return {
        "status": "completed",
        **sync_result,
    }
