"""
Typed HTTP client for the Money Clarity FastAPI backend.

All requests automatically include the Supabase access_token as Bearer token.
Token refresh is attempted once on 401 before giving up.

Usage:
    client = ApiClient(access_token, refresh_token)
    result = await client.get_summary()
"""

import io
from dataclasses import dataclass
from typing import Optional

import httpx
import streamlit as st


def _backend_url() -> str:
    return st.secrets.get("BACKEND_URL", "http://localhost:8000")


@dataclass
class MonthlySummary:
    month: str
    income: float
    expense: float
    net: float
    categories: dict


class ApiClient:
    def __init__(self, access_token: str, refresh_fn=None):
        self.access_token = access_token
        self._refresh_fn = refresh_fn  # callable() -> new access_token or None

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    async def _get(self, path: str, **kwargs) -> dict | list:
        async with httpx.AsyncClient(base_url=_backend_url(), timeout=30) as client:
            resp = await client.get(path, headers=self._headers(), **kwargs)
            if resp.status_code == 401 and self._refresh_fn:
                new_token = self._refresh_fn()
                if new_token:
                    self.access_token = new_token
                    resp = await client.get(path, headers=self._headers(), **kwargs)
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, **kwargs) -> dict | list:
        async with httpx.AsyncClient(base_url=_backend_url(), timeout=60) as client:
            resp = await client.post(path, headers=self._headers(), **kwargs)
            if resp.status_code == 401 and self._refresh_fn:
                new_token = self._refresh_fn()
                if new_token:
                    self.access_token = new_token
                    resp = await client.post(path, headers=self._headers(), **kwargs)
            resp.raise_for_status()
            return resp.json()

    async def upload_file(self, file_bytes: bytes, filename: str) -> dict:
        """POST /upload — upload and encrypt a bank statement."""
        return await self._post(
            "/upload",
            files={"file": (filename, io.BytesIO(file_bytes), "application/octet-stream")},
        )

    async def parse_upload(self, upload_id: str) -> dict:
        """POST /parse — parse a previously uploaded file."""
        return await self._post("/parse", json={"upload_id": upload_id})

    async def get_summary(self, month: Optional[str] = None) -> list[MonthlySummary]:
        """GET /summary — retrieve monthly aggregates."""
        params = {"month": month} if month else {}
        data = await self._get("/summary", params=params)
        return [MonthlySummary(**row) for row in data]

    async def get_gmail_status(self) -> dict:
        """GET /gmail/status — check if Gmail is connected."""
        return await self._get("/gmail/status")

    async def get_gmail_connect_url(self) -> str:
        """GET /gmail/connect — get the Google OAuth URL."""
        data = await self._get("/gmail/connect")
        return data["auth_url"]

    async def sync_gmail(self, since: Optional[str] = None) -> dict:
        """POST /gmail/sync — trigger incremental Gmail sync."""
        body = {}
        if since:
            body["since"] = since
        return await self._post("/gmail/sync", json=body)
