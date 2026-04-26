"""
POST /parse  — parse a previously uploaded file and insert transactions.

Contract:
  Method : POST application/json
  Headers: Authorization: Bearer <supabase_access_token>
  Body   : {"upload_id": "uuid"}
  Response 200:
    {
      "upload_id": "uuid",
      "parsed_rows": 150,
      "inserted": 150,
      "month_range": ["2024-01", "2024-06"]
    }
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.auth import UserId
from backend.crypto import decrypt_bytes
from backend.services.parser_service import parse_statement
from backend.services.supabase_client import admin_client

router = APIRouter(prefix="/parse", tags=["parse"])


class ParseRequest(BaseModel):
    upload_id: str


@router.post("")
async def parse_upload(body: ParseRequest, user_id: UserId):
    """Decrypt a stored file, parse transactions, and insert into statements table."""
    client = await admin_client()

    # Fetch upload record — verify ownership
    result = (
        await client.table("uploads")
        .select("*")
        .eq("id", body.upload_id)
        .eq("user_id", user_id)  # ownership check
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Upload not found")

    upload = result.data
    if upload["status"] == "parsed":
        # Idempotent — return existing count
        existing = (
            await client.table("statements")
            .select("id", count="exact")
            .eq("upload_id", body.upload_id)
            .execute()
        )
        count = existing.count or 0
        return {"upload_id": body.upload_id, "parsed_rows": count, "inserted": 0, "status": "already_parsed"}

    # Retrieve encrypted file from Supabase Storage
    try:
        storage_response = await client.storage.from_("statements").download(upload["storage_path"])
        encrypted_content = storage_response
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve file: {exc}") from exc

    # Decrypt — returns original raw bytes (works for both CSV and binary XLSX)
    try:
        file_bytes = decrypt_bytes(encrypted_content.decode())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Decryption failed: {exc}") from exc

    # Parse
    try:
        df = parse_statement(file_bytes, upload["filename"])
    except Exception as exc:
        await client.table("uploads").update({"status": "parse_failed"}).eq("id", body.upload_id).execute()
        raise HTTPException(status_code=422, detail=f"Parse error: {exc}") from exc

    rows = df.to_dict(orient="records")
    tx_rows = [
        {
            "user_id": user_id,
            "upload_id": body.upload_id,
            "date": str(r["date"].date()) if hasattr(r["date"], "date") else str(r["date"]),
            "description": str(r["description"]),
            "debit": float(r["debit"]),
            "credit": float(r["credit"]),
            "category": r["category"],
            "type": r["type"],
            "month": r["month"],
            "source": r["source"],
        }
        for r in rows
    ]

    if tx_rows:
        await client.table("statements").insert(tx_rows).execute()

    months = sorted(df["month"].unique().tolist())
    await client.table("uploads").update(
        {"status": "parsed", "updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", body.upload_id).execute()

    return {
        "upload_id": body.upload_id,
        "parsed_rows": len(rows),
        "inserted": len(tx_rows),
        "month_range": [months[0], months[-1]] if months else [],
    }
