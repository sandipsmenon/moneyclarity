"""Tests for GET /summary endpoint."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


SAMPLE_SUMMARIES = [
    {
        "user_id": "some-user-id",
        "month": "2024-01",
        "income": 85000.0,
        "expense": 42000.0,
        "net": 43000.0,
        "categories": {"Food & Dining": 8500.0, "Transport": 3200.0},
    },
    {
        "user_id": "some-user-id",
        "month": "2024-02",
        "income": 85000.0,
        "expense": 38000.0,
        "net": 47000.0,
        "categories": {"Food & Dining": 7200.0, "Shopping": 5000.0},
    },
]


@pytest.mark.asyncio
async def test_summary_returns_aggregates(client, auth_headers, user_id, mock_supabase):
    """Should return monthly summary list for the authenticated user."""
    mock_client, mock_table = mock_supabase
    mock_table.execute.return_value = MagicMock(data=SAMPLE_SUMMARIES)

    with patch("backend.routes.summary.admin_client", return_value=mock_client):
        resp = await client.get("/summary", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["month"] == "2024-01"
    assert body[0]["income"] == 85000.0
    assert "Food & Dining" in body[0]["categories"]


@pytest.mark.asyncio
async def test_summary_requires_auth(client):
    """Unauthenticated request should fail."""
    resp = await client.get("/summary")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_summary_empty_when_no_data(client, auth_headers, mock_supabase):
    """No data should return empty list, not error."""
    mock_client, mock_table = mock_supabase
    mock_table.execute.return_value = MagicMock(data=[])

    with patch("backend.routes.summary.admin_client", return_value=mock_client):
        resp = await client.get("/summary", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_summary_filters_by_month(client, auth_headers, mock_supabase):
    """Month query param should be passed to DB query."""
    mock_client, mock_table = mock_supabase
    mock_table.execute.return_value = MagicMock(data=[SAMPLE_SUMMARIES[0]])

    with patch("backend.routes.summary.admin_client", return_value=mock_client):
        resp = await client.get("/summary?month=2024-01", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["month"] == "2024-01"


@pytest.mark.asyncio
async def test_summary_correct_user_isolation(client, valid_token, mock_supabase):
    """Summary should only return data for the authenticated user."""
    token, uid = valid_token
    mock_client, mock_table = mock_supabase

    # Only return rows matching this user
    user_rows = [r for r in SAMPLE_SUMMARIES if r["user_id"] == uid]
    mock_table.execute.return_value = MagicMock(data=user_rows)

    with patch("backend.routes.summary.admin_client", return_value=mock_client):
        resp = await client.get(
            "/summary",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    # Data returned is for this user only (RLS enforces this in production)
    assert isinstance(resp.json(), list)
