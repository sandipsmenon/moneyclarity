"""
Supabase client helpers.

- admin_client() : uses service_role key — bypass RLS for server operations
- user_client(token) : uses anon key + user JWT — RLS enforced, safe for user data

Always use user_client for user-scoped queries so RLS is enforced.
Use admin_client ONLY for privileged server operations (e.g. inserting as service).
"""

from functools import lru_cache

from supabase import AsyncClient, acreate_client

from backend.config import get_settings


@lru_cache(maxsize=1)
def _get_admin_client_sync() -> AsyncClient:
    # Placeholder — actual async client created per-request below
    pass


async def admin_client() -> AsyncClient:
    """Service-role client — bypasses RLS."""
    settings = get_settings()
    return await acreate_client(settings.supabase_url, settings.supabase_service_role_key)


async def user_client(access_token: str) -> AsyncClient:
    """Anon-key client with user JWT injected — RLS enforced."""
    settings = get_settings()
    client = await acreate_client(settings.supabase_url, settings.supabase_anon_key)
    # Inject user token so auth.uid() resolves correctly in RLS policies
    await client.auth.set_session(access_token, "")
    return client


async def upload_file(
    bucket: str,
    path: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload file to Supabase Storage using service role. Returns storage path."""
    client = await admin_client()
    await client.storage.from_(bucket).upload(
        path=path,
        file=data,
        file_options={"content-type": content_type, "upsert": "true"},
    )
    return path


async def get_signed_url(bucket: str, path: str, expires_in: int = 3600) -> str:
    """Generate a signed download URL."""
    client = await admin_client()
    result = await client.storage.from_(bucket).create_signed_url(path, expires_in)
    return result["signedURL"]
