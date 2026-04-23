"""Tests for POST /upload endpoint."""

import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_upload_csv_success(client, auth_headers, user_id, mock_supabase, sample_csv_bytes):
    """Happy path: upload a valid CSV file."""
    mock_client, mock_table = mock_supabase

    # upload_file should not raise
    with patch("backend.routes.upload.upload_file", new_callable=AsyncMock):
        with patch("backend.routes.upload.admin_client", return_value=mock_client):
            mock_table.execute.return_value = MagicMock(data={"id": str(uuid.uuid4())})

            resp = await client.post(
                "/upload",
                headers=auth_headers,
                files={"file": ("statement.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "uploaded"
    assert "upload_id" in body
    assert "storage_path" in body
    assert user_id in body["storage_path"]


@pytest.mark.asyncio
async def test_upload_requires_auth(client, sample_csv_bytes):
    """Unauthenticated request should return 403."""
    resp = await client.post(
        "/upload",
        files={"file": ("statement.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_upload_invalid_file_type(client, auth_headers):
    """Non-spreadsheet file should return 400."""
    resp = await client.post(
        "/upload",
        headers=auth_headers,
        files={"file": ("report.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert resp.status_code == 400
    assert "CSV" in resp.json()["detail"] or "Excel" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_file_too_large(client, auth_headers):
    """Files > 20MB should return 413."""
    big_file = b"x" * (21 * 1024 * 1024)
    resp = await client.post(
        "/upload",
        headers=auth_headers,
        files={"file": ("big.csv", io.BytesIO(big_file), "text/csv")},
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_upload_xlsx_accepted(client, auth_headers, mock_supabase):
    """XLSX files should be accepted."""
    mock_client, mock_table = mock_supabase
    fake_xlsx = b"PK\x03\x04"  # ZIP magic bytes (XLSX is a zip)

    with patch("backend.routes.upload.upload_file", new_callable=AsyncMock):
        with patch("backend.routes.upload.admin_client", return_value=mock_client):
            resp = await client.post(
                "/upload",
                headers=auth_headers,
                files={"file": ("statement.xlsx", io.BytesIO(fake_xlsx),
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

    # Accepted (even if not a real XLSX — extension check passes)
    assert resp.status_code == 200
