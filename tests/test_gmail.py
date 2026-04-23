"""Tests for Gmail OAuth endpoints and crypto helpers."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.crypto import decrypt, encrypt, reencrypt_value


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests: crypto helpers
# ─────────────────────────────────────────────────────────────────────────────

def test_encrypt_decrypt_roundtrip():
    plaintext = "my-secret-gmail-token-abc123"
    token = encrypt(plaintext)
    assert plaintext not in token  # Not stored in plaintext
    assert decrypt(token) == plaintext


def test_encrypt_produces_different_nonces():
    plaintext = "same-value"
    t1 = encrypt(plaintext)
    t2 = encrypt(plaintext)
    assert t1 != t2  # Different nonces → different ciphertext


def test_reencrypt_same_key_returns_none():
    token = encrypt("value")
    assert reencrypt_value(token) is None  # already on latest key


def test_decrypt_invalid_token_raises():
    with pytest.raises(ValueError):
        decrypt("not-a-valid-token")


# ─────────────────────────────────────────────────────────────────────────────
# /gmail/connect endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gmail_connect_returns_auth_url(client, auth_headers):
    """Should return a Google OAuth URL."""
    mock_flow = MagicMock()
    mock_flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth?...", "state123")

    with patch("backend.routes.gmail._build_flow", return_value=mock_flow):
        resp = await client.get("/gmail/connect", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert "auth_url" in body
    assert "accounts.google.com" in body["auth_url"]


@pytest.mark.asyncio
async def test_gmail_connect_requires_auth(client):
    """Unauthenticated request should fail."""
    resp = await client.get("/gmail/connect")
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# /gmail/callback endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gmail_callback_invalid_state(client):
    """Invalid state param should return 400."""
    resp = await client.get("/gmail/callback?code=authcode&state=invalid-state-xyz")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_gmail_callback_error_param(client):
    """Google error should redirect with error."""
    resp = await client.get(
        "/gmail/callback?error=access_denied&state=any",
        follow_redirects=False,
    )
    assert resp.status_code == 307
    assert "gmail_error" in resp.headers["location"]


# ─────────────────────────────────────────────────────────────────────────────
# /gmail/status endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gmail_status_not_connected(client, auth_headers, mock_supabase):
    mock_client, mock_table = mock_supabase
    mock_table.execute.return_value = MagicMock(data=None)

    with patch("backend.routes.gmail.admin_client", return_value=mock_client):
        resp = await client.get("/gmail/status", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["connected"] is False


@pytest.mark.asyncio
async def test_gmail_status_connected(client, auth_headers, user_id, mock_supabase):
    mock_client, mock_table = mock_supabase
    mock_table.execute.return_value = MagicMock(data={
        "gmail_user_id": "test@gmail.com",
        "last_synced_at": "2024-01-15T10:00:00Z",
        "scope": "https://www.googleapis.com/auth/gmail.readonly",
    })

    with patch("backend.routes.gmail.admin_client", return_value=mock_client):
        resp = await client.get("/gmail/status", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["gmail_user_id"] == "test@gmail.com"


# ─────────────────────────────────────────────────────────────────────────────
# /gmail/sync endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gmail_sync_not_connected(client, auth_headers, mock_supabase):
    """Sync when Gmail not connected should return 400."""
    mock_client, mock_table = mock_supabase
    mock_table.execute.return_value = MagicMock(data=None)

    with patch("backend.routes.gmail.admin_client", return_value=mock_client):
        resp = await client.post("/gmail/sync", headers=auth_headers, json={})

    assert resp.status_code == 400
    assert "not connected" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_gmail_sync_success(client, auth_headers, user_id, mock_supabase):
    """Successful sync should return new_files and transactions_imported counts."""
    mock_client, mock_table = mock_supabase
    # Gmail is connected
    mock_table.execute.return_value = MagicMock(data={"last_synced_at": None})

    sync_result = {"new_files": 2, "transactions_imported": 45, "errors": []}

    with patch("backend.routes.gmail.admin_client", return_value=mock_client):
        with patch("backend.routes.gmail.run_gmail_sync", new_callable=AsyncMock, return_value=sync_result):
            resp = await client.post("/gmail/sync", headers=auth_headers, json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["new_files"] == 2
    assert body["transactions_imported"] == 45
