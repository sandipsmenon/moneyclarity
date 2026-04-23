"""
GET /summary  — return monthly aggregates for the authenticated user.

Contract:
  Method : GET
  Headers: Authorization: Bearer <supabase_access_token>
  Query  : ?month=2024-01 (optional, filter single month)
  Response 200:
    [
      {
        "month": "2024-01",
        "income": 85000.0,
        "expense": 42000.0,
        "net": 43000.0,
        "categories": {
          "Food & Dining": 8500.0,
          "Transport": 3200.0,
          ...
        }
      }
    ]

Data source: monthly_summaries table (updated by DB trigger on statements insert).
Falls back to computing from statements if monthly_summaries is empty.
"""

import json
from typing import Optional

from fastapi import APIRouter, Query

from backend.auth import UserId
from backend.services.supabase_client import admin_client

router = APIRouter(prefix="/summary", tags=["summary"])


@router.get("")
async def get_summary(
    user_id: UserId,
    month: Optional[str] = Query(None, description="Filter by month YYYY-MM"),
):
    """Return monthly financial aggregates for the authenticated user."""
    client = await admin_client()

    query = (
        client.table("monthly_summaries")
        .select("*")
        .eq("user_id", user_id)
        .order("month", desc=False)
    )
    if month:
        query = query.eq("month", month)

    result = await query.execute()
    rows = result.data or []

    if not rows:
        # Fallback: compute from raw statements (handles case where trigger hasn't run)
        rows = await _compute_from_statements(user_id, client, month)

    return [
        {
            "month": r["month"],
            "income": float(r["income"]),
            "expense": float(r["expense"]),
            "net": float(r["net"]),
            "categories": r["categories"] if isinstance(r["categories"], dict)
                          else json.loads(r["categories"] or "{}"),
        }
        for r in rows
    ]


async def _compute_from_statements(user_id: str, client, month: Optional[str]) -> list[dict]:
    """Fallback aggregation directly from statements table."""
    query = (
        client.table("statements")
        .select("month, type, debit, credit, category")
        .eq("user_id", user_id)
    )
    if month:
        query = query.eq("month", month)

    result = await query.execute()
    rows = result.data or []

    aggregates: dict[str, dict] = {}
    for row in rows:
        m = row["month"]
        if m not in aggregates:
            aggregates[m] = {"month": m, "income": 0.0, "expense": 0.0, "categories": {}}

        if row["type"] == "income":
            aggregates[m]["income"] += float(row["credit"])
        else:
            aggregates[m]["expense"] += float(row["debit"])
            cat = row["category"] or "Other"
            aggregates[m]["categories"][cat] = (
                aggregates[m]["categories"].get(cat, 0.0) + float(row["debit"])
            )

    for m, agg in aggregates.items():
        agg["net"] = round(agg["income"] - agg["expense"], 2)
        agg["income"] = round(agg["income"], 2)
        agg["expense"] = round(agg["expense"], 2)
        agg["categories"] = {k: round(v, 2) for k, v in agg["categories"].items()}

    return sorted(aggregates.values(), key=lambda x: x["month"])
