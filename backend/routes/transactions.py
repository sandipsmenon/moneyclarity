"""GET /transactions — raw transaction rows for the authenticated user."""

from fastapi import APIRouter, Query

from backend.auth import UserId
from backend.services.supabase_client import admin_client

router = APIRouter(prefix="/transactions", tags=["transactions"])

_MAX_ROWS = 10_000


@router.get("")
async def get_transactions(
    user_id: UserId,
    limit: int = Query(default=_MAX_ROWS, le=_MAX_ROWS),
) -> list[dict]:
    """Return transaction rows for the authenticated user, ordered by date."""
    client = await admin_client()
    result = (
        await client.table("statements")
        .select("date, description, debit, credit, category, type, month, source")
        .eq("user_id", user_id)
        .order("date", desc=False)
        .limit(limit)
        .execute()
    )
    rows = result.data or []
    return [
        {
            "date":        r["date"],
            "description": r["description"],
            "debit":       float(r["debit"]),
            "credit":      float(r["credit"]),
            "category":    r["category"] or "Other",
            "type":        r["type"],
            "month":       r["month"],
            "source":      r["source"] or "",
        }
        for r in rows
    ]
