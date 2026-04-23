"""
POST /upload  — encrypt and store a bank statement file.

Contract:
  Method : POST multipart/form-data
  Headers: Authorization: Bearer <supabase_access_token>
  Body   : file (UploadFile), metadata (optional JSON string)
  Response 200:
    {
      "upload_id": "uuid",
      "storage_path": "user_id/upload_id/filename.xlsx",
      "status": "uploaded"
    }
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from backend.auth import UserId
from backend.crypto import encrypt as enc_val
from backend.services.supabase_client import admin_client, upload_file

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("")
async def upload_statement(
    user_id: UserId,
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None),
):
    """Upload and encrypt a bank statement file to Supabase Storage."""
    allowed_types = {"text/csv", "application/vnd.ms-excel",
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    content_type = file.content_type or ""

    # Validate by extension if MIME type is generic
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("csv", "xlsx", "xls") and content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only CSV and Excel files are supported")

    file_bytes = await file.read()
    if len(file_bytes) > 20 * 1024 * 1024:  # 20 MB limit
        raise HTTPException(status_code=413, detail="File exceeds 20 MB limit")

    upload_id = str(uuid.uuid4())
    storage_path = f"{user_id}/{upload_id}/{filename}"

    # Encrypt file bytes before storing
    encrypted_content = enc_val(file_bytes).encode()

    try:
        await upload_file(
            bucket="statements",
            path=storage_path,
            data=encrypted_content,
            content_type="application/octet-stream",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Storage error: {exc}") from exc

    meta = {}
    if metadata:
        try:
            meta = json.loads(metadata)
        except json.JSONDecodeError:
            pass

    client = await admin_client()
    await client.table("uploads").insert({
        "id": upload_id,
        "user_id": user_id,
        "filename": filename,
        "storage_path": storage_path,
        "source": meta.get("source", "manual"),
        "status": "uploaded",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    return {
        "upload_id": upload_id,
        "storage_path": storage_path,
        "status": "uploaded",
    }
