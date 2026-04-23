"""
Background task: Gmail sync pipeline.

MVP: Uses FastAPI BackgroundTasks (in-process, no queue).
Scale path: replace with Celery task (see backend/workers/celery_app.py).

Pipeline:
  1. Fetch statement attachments from Gmail
  2. Encrypt + upload raw files to Supabase Storage
  3. Parse transactions from each attachment
  4. Upsert transactions into `statements` table
  5. Update gmail_accounts.last_synced_at
  6. Write sync result to sync_log table
"""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from backend.services.gmail_service import fetch_statement_attachments, update_last_synced
from backend.services.parser_service import parse_statement
from backend.services.supabase_client import admin_client, upload_file
from backend.crypto import encrypt as enc_val


async def run_gmail_sync(user_id: str, since: Optional[datetime] = None) -> dict:
    """
    Full Gmail sync for a user. Returns summary of what was imported.
    Called from /gmail/sync endpoint via BackgroundTasks (or directly for sync response).
    """
    new_files = 0
    transactions_imported = 0
    errors: list[str] = []

    try:
        attachments = await fetch_statement_attachments(user_id, since=since)
    except Exception as exc:
        return {"error": str(exc), "new_files": 0, "transactions_imported": 0}

    client = await admin_client()

    for att in attachments:
        filename: str = att["filename"]
        file_bytes: bytes = att["data"]
        message_id: str = att["message_id"]

        # Deduplicate by Gmail message_id + filename
        dedup_hash = hashlib.sha256(f"{message_id}:{filename}".encode()).hexdigest()
        existing = (
            await client.table("uploads")
            .select("id")
            .eq("user_id", user_id)
            .eq("dedup_hash", dedup_hash)
            .execute()
        )
        if existing.data:
            continue  # already processed

        upload_id = str(uuid.uuid4())
        storage_path = f"{user_id}/{upload_id}/{filename}"

        # Encrypt file bytes before storage
        encrypted_content = enc_val(file_bytes).encode()

        try:
            await upload_file(
                bucket="statements",
                path=storage_path,
                data=encrypted_content,
                content_type="application/octet-stream",
            )
        except Exception as exc:
            errors.append(f"Storage upload failed for {filename}: {exc}")
            continue

        # Record upload
        await client.table("uploads").insert({
            "id": upload_id,
            "user_id": user_id,
            "filename": filename,
            "storage_path": storage_path,
            "source": "gmail",
            "gmail_message_id": message_id,
            "dedup_hash": dedup_hash,
            "status": "uploaded",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        new_files += 1

        # Parse and insert transactions
        try:
            df = parse_statement(file_bytes, filename)
        except Exception as exc:
            errors.append(f"Parse failed for {filename}: {exc}")
            await client.table("uploads").update({"status": "parse_failed"}).eq("id", upload_id).execute()
            continue

        rows = df.to_dict(orient="records")
        tx_rows = [
            {
                "user_id": user_id,
                "upload_id": upload_id,
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
            transactions_imported += len(tx_rows)

        await client.table("uploads").update({"status": "parsed"}).eq("id", upload_id).execute()

    await update_last_synced(user_id)

    return {
        "new_files": new_files,
        "transactions_imported": transactions_imported,
        "errors": errors,
    }
