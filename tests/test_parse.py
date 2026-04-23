"""Tests for POST /parse endpoint and parser_service."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.parser_service import categorize, compute_monthly_summary, parse_statement


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests: parser_service
# ─────────────────────────────────────────────────────────────────────────────

def test_categorize_food():
    assert categorize("ZOMATO ORDER PAYMENT") == "Food & Dining"


def test_categorize_transport():
    assert categorize("UBER RIDE COMPLETED") == "Transport"


def test_categorize_salary():
    assert categorize("SALARY CREDIT NEFT") == "Salary / Income"


def test_categorize_unknown():
    assert categorize("MISCELLANEOUS PAYMENT XYZ") == "Other"


def test_parse_statement_csv(sample_csv_bytes):
    df = parse_statement(sample_csv_bytes, "test.csv")
    assert len(df) == 5
    assert set(df.columns) >= {"date", "description", "debit", "credit", "category", "type", "month"}
    # Salary row should be income
    salary_row = df[df["description"].str.contains("SALARY")]
    assert len(salary_row) == 1
    assert salary_row.iloc[0]["type"] == "income"
    assert salary_row.iloc[0]["credit"] == 85000.0


def test_parse_statement_categories(sample_csv_bytes):
    df = parse_statement(sample_csv_bytes, "test.csv")
    zomato_row = df[df["description"].str.contains("ZOMATO")]
    assert zomato_row.iloc[0]["category"] == "Food & Dining"

    amazon_row = df[df["description"].str.contains("AMAZON")]
    assert amazon_row.iloc[0]["category"] == "Shopping"


def test_compute_monthly_summary(sample_csv_bytes):
    df = parse_statement(sample_csv_bytes, "test.csv")
    summaries = compute_monthly_summary(df)
    assert len(summaries) == 1
    jan = summaries[0]
    assert jan["month"] == "2024-01"
    assert jan["income"] == 85000.0
    assert jan["expense"] > 0
    assert "Food & Dining" in jan["categories"]


def test_parse_statement_unsupported_type():
    with pytest.raises(ValueError, match="Unsupported file type"):
        parse_statement(b"content", "file.pdf")


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests: /parse endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_parse_endpoint_success(client, auth_headers, user_id, mock_supabase, sample_csv_bytes):
    """Parse a valid upload."""
    mock_client, mock_table = mock_supabase
    upload_id = str(uuid.uuid4())

    from backend.crypto import encrypt
    encrypted = encrypt(sample_csv_bytes).encode()

    # Mock: fetch upload record
    upload_row = {
        "id": upload_id,
        "user_id": user_id,
        "filename": "test.csv",
        "storage_path": f"{user_id}/{upload_id}/test.csv",
        "status": "uploaded",
    }
    mock_table.execute.return_value = MagicMock(data=upload_row)

    # Mock: storage download
    mock_client.storage.from_.return_value.download = AsyncMock(return_value=encrypted)

    # Mock: statements insert and upload update
    insert_mock = MagicMock(data=None)
    update_mock = MagicMock(data=None)
    mock_table.insert.return_value.execute = AsyncMock(return_value=insert_mock)
    mock_table.update.return_value.eq.return_value.execute = AsyncMock(return_value=update_mock)

    with patch("backend.routes.parse.admin_client", return_value=mock_client):
        resp = await client.post(
            "/parse",
            headers=auth_headers,
            json={"upload_id": upload_id},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["upload_id"] == upload_id
    assert body["parsed_rows"] == 5
    assert body["inserted"] == 5


@pytest.mark.asyncio
async def test_parse_wrong_user_returns_404(client, auth_headers, mock_supabase):
    """A user cannot parse another user's upload."""
    mock_client, mock_table = mock_supabase
    mock_table.execute.return_value = MagicMock(data=None)  # Not found for this user

    with patch("backend.routes.parse.admin_client", return_value=mock_client):
        resp = await client.post(
            "/parse",
            headers=auth_headers,
            json={"upload_id": str(uuid.uuid4())},
        )

    assert resp.status_code == 404
