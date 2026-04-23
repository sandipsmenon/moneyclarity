"""
Optional Celery worker for scaled Gmail sync.

Usage (when REDIS_URL is set):
  # Start worker
  celery -A backend.workers.celery_app worker --loglevel=info

  # Start beat scheduler (for nightly syncs)
  celery -A backend.workers.celery_app beat --loglevel=info

To switch from BackgroundTasks to Celery in gmail.py:
  Replace `await run_gmail_sync(user_id, since)` with
  `sync_gmail_task.delay(user_id, since.isoformat() if since else None)`
"""

import asyncio

from celery import Celery
from celery.schedules import crontab

from backend.config import get_settings

settings = get_settings()

celery = Celery(
    "moneyclarity",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        # Sync all connected Gmail accounts nightly at 2 AM UTC
        "nightly-gmail-sync": {
            "task": "backend.workers.celery_app.sync_all_gmail_accounts",
            "schedule": crontab(hour=2, minute=0),
        },
    },
)


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def sync_gmail_task(self, user_id: str, since_iso: str | None = None):
    """Celery task: sync Gmail for a single user."""
    from datetime import datetime, timezone
    from backend.services.background_tasks import run_gmail_sync

    since = None
    if since_iso:
        since = datetime.fromisoformat(since_iso).replace(tzinfo=timezone.utc)

    try:
        result = asyncio.run(run_gmail_sync(user_id, since=since))
        return result
    except Exception as exc:
        raise self.retry(exc=exc)


@celery.task
def sync_all_gmail_accounts():
    """Nightly task: sync all users who have Gmail connected."""
    from backend.services.supabase_client import admin_client

    async def _run():
        client = await admin_client()
        result = await client.table("gmail_accounts").select("user_id").execute()
        user_ids = [r["user_id"] for r in (result.data or [])]
        for uid in user_ids:
            sync_gmail_task.delay(uid)
        return len(user_ids)

    count = asyncio.run(_run())
    return {"scheduled": count}
