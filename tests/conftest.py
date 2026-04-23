"""
Shared test fixtures for Money Clarity backend tests.

Uses:
  - pytest-asyncio for async tests
  - httpx AsyncClient against FastAPI (no real network)
  - unittest.mock for Supabase and Google API calls
"""

import base64
import os
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set test env vars BEFORE importing app (avoids config validation errors)
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "super-secret-jwt-signing-key-for-tests")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-google-client-secret")
os.environ.setdefault("OAUTH_REDIRECT_URL", "http://localhost:8000/gmail/callback")
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    base64.b64encode(b"test-32-byte-encryption-key12345").decode(),
)
os.environ.setdefault("ENVIRONMENT", "test")

from backend.main import app


def make_jwt(user_id: str = None, secret: str = "super-secret-jwt-signing-key-for-tests") -> str:
    """Create a valid test JWT signed with the test secret."""
    uid = user_id or str(uuid.uuid4())
    payload = {
        "sub": uid,
        "aud": "authenticated",
        "role": "authenticated",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
    }
    return jwt.encode(payload, secret, algorithm="HS256"), uid


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async test client for the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
def valid_token() -> tuple[str, str]:
    """Return (token, user_id) for a test user."""
    return make_jwt()


@pytest.fixture
def auth_headers(valid_token) -> dict:
    """Return Authorization headers for the test user."""
    token, _ = valid_token
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_id(valid_token) -> str:
    _, uid = valid_token
    return uid


@pytest.fixture
def mock_supabase():
    """Mock the Supabase admin client to avoid real network calls."""
    mock_client = AsyncMock()
    mock_table = AsyncMock()

    # Chain: client.table(...).select(...).eq(...).execute() -> AsyncMock
    mock_table.select.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.update.return_value = mock_table
    mock_table.upsert.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.single.return_value = mock_table
    mock_table.maybe_single.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.execute = AsyncMock(return_value=MagicMock(data=[], count=0))

    mock_client.table.return_value = mock_table
    mock_client.storage = AsyncMock()
    mock_client.storage.from_.return_value = AsyncMock()

    with patch("backend.services.supabase_client.admin_client", return_value=mock_client):
        with patch("backend.services.supabase_client.upload_file", new_callable=AsyncMock):
            yield mock_client, mock_table


@pytest.fixture
def sample_csv_bytes() -> bytes:
    """Minimal valid bank statement CSV."""
    content = """Date,Description,Debit,Credit
01/01/2024,ZOMATO ORDER,350.00,
02/01/2024,SALARY CREDIT,,85000.00
03/01/2024,AMAZON SHOPPING,1200.00,
04/01/2024,UBER RIDE,250.00,
05/01/2024,NETFLIX SUBSCRIPTION,649.00,
"""
    return content.encode("utf-8")
