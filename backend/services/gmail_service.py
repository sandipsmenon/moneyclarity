"""
Gmail API service: token management, message fetching, attachment extraction.

Tokens are stored encrypted in the gmail_accounts table.
Refresh is handled transparently when access_token is expired.
"""

import base64
import io
import json
from datetime import datetime, timezone
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from backend.config import get_settings
from backend.crypto import decrypt, encrypt
from backend.services.supabase_client import admin_client

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "email",
    "profile",
]

# Email subjects / senders indicating a bank statement attachment
STATEMENT_PATTERNS = [
    "account statement",
    "e-statement",
    "monthly statement",
    "bank statement",
    "hdfc bank",
    "icici bank",
    "axis bank",
    "kotak bank",
    "sbi statement",
    "paytm payments bank",
]

ATTACHMENT_EXTENSIONS = {".csv", ".xlsx", ".xls", ".pdf"}


async def store_gmail_tokens(
    user_id: str,
    gmail_user_id: str,
    credentials: Credentials,
    scope: str,
) -> None:
    """Encrypt and upsert Gmail OAuth tokens for a user."""
    client = await admin_client()

    access_token_enc = encrypt(credentials.token)
    refresh_token_enc = encrypt(credentials.refresh_token or "")
    token_expiry = credentials.expiry.isoformat() if credentials.expiry else None

    await client.table("gmail_accounts").upsert(
        {
            "user_id": user_id,
            "gmail_user_id": gmail_user_id,
            "access_token_enc": access_token_enc,
            "refresh_token_enc": refresh_token_enc,
            "scope": scope,
            "token_expiry": token_expiry,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id",
    ).execute()


async def get_gmail_credentials(user_id: str) -> Optional[Credentials]:
    """Retrieve and decrypt Gmail credentials for a user, refreshing if expired."""
    settings = get_settings()
    client = await admin_client()

    result = (
        await client.table("gmail_accounts")
        .select("*")
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if not result.data:
        return None

    row = result.data
    access_token = decrypt(row["access_token_enc"])
    refresh_token = decrypt(row["refresh_token_enc"]) if row["refresh_token_enc"] else None
    expiry = datetime.fromisoformat(row["token_expiry"]) if row["token_expiry"] else None

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=GMAIL_SCOPES,
        expiry=expiry,
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Persist refreshed tokens
        await store_gmail_tokens(
            user_id=user_id,
            gmail_user_id=row["gmail_user_id"],
            credentials=creds,
            scope=row["scope"],
        )

    return creds


def _is_statement_email(subject: str, sender: str) -> bool:
    subject_lower = subject.lower()
    sender_lower = sender.lower()
    return any(
        pat in subject_lower or pat in sender_lower for pat in STATEMENT_PATTERNS
    )


def _get_attachment_data(service, msg_id: str, attachment_id: str) -> bytes:
    att = service.users().messages().attachments().get(
        userId="me", messageId=msg_id, id=attachment_id
    ).execute()
    return base64.urlsafe_b64decode(att["data"])


async def fetch_statement_attachments(
    user_id: str,
    since: Optional[datetime] = None,
) -> list[dict]:
    """
    Fetch bank statement attachments from Gmail for a user.
    Returns list of {filename, data: bytes, message_id, received_at}.
    """
    creds = await get_gmail_credentials(user_id)
    if not creds:
        raise ValueError("Gmail not connected for this user")

    service = build("gmail", "v1", credentials=creds)

    query_parts = ["has:attachment"]
    if since:
        ts = int(since.timestamp())
        query_parts.append(f"after:{ts}")
    else:
        query_parts.append("newer_than:90d")

    # Add OR filter for bank-related senders
    bank_query = " OR ".join(
        [f'from:{p.replace(" ", "")}' for p in ["hdfcbank", "icicibank", "axisbank", "kotakbank"]]
    )
    query_parts.append(f"({bank_query})")
    query = " ".join(query_parts)

    attachments = []
    page_token = None

    while True:
        params = {"userId": "me", "q": query, "maxResults": 50}
        if page_token:
            params["pageToken"] = page_token

        try:
            results = service.users().messages().list(**params).execute()
        except HttpError as e:
            raise RuntimeError(f"Gmail API error: {e}") from e

        messages = results.get("messages", [])
        for msg_ref in messages:
            msg = service.users().messages().get(
                userId="me", messageId=msg_ref["id"], format="full"
            ).execute()

            headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
            subject = headers.get("Subject", "")
            sender = headers.get("From", "")
            date_str = headers.get("Date", "")

            if not _is_statement_email(subject, sender):
                continue

            parts = msg["payload"].get("parts", [])
            for part in parts:
                filename = part.get("filename", "")
                if not filename:
                    continue
                ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                if ext not in ATTACHMENT_EXTENSIONS:
                    continue

                att_id = part.get("body", {}).get("attachmentId")
                if not att_id:
                    continue

                data = _get_attachment_data(service, msg_ref["id"], att_id)
                attachments.append({
                    "filename": filename,
                    "data": data,
                    "message_id": msg_ref["id"],
                    "received_at": date_str,
                })

        page_token = results.get("nextPageToken")
        if not page_token:
            break

    return attachments


async def update_last_synced(user_id: str) -> None:
    client = await admin_client()
    await client.table("gmail_accounts").update(
        {"last_synced_at": datetime.now(timezone.utc).isoformat()}
    ).eq("user_id", user_id).execute()
