"""
Encryption key rotation script.

Run when rotating the ENCRYPTION_SECRET to a new key:

1. Add the new key to ENCRYPTION_KEYS env var:
   ENCRYPTION_KEYS="v1:<old_b64_key>,v2:<new_b64_key>"
   ENCRYPTION_SECRET=<new_b64_key>  (active key for new records)

2. Run this script to re-encrypt all existing records with v2:
   python scripts/rotate_encryption_keys.py

3. After confirming all records are re-encrypted, remove the old key:
   ENCRYPTION_KEYS="v2:<new_b64_key>"

The script is idempotent — running it twice on already-rotated records is a no-op.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backend.crypto import reencrypt_value
from backend.services.supabase_client import admin_client


ENCRYPTED_COLUMNS = [
    ("gmail_accounts", "access_token_enc", "id"),
    ("gmail_accounts", "refresh_token_enc", "id"),
]


async def rotate_table(client, table: str, column: str, pk: str) -> dict:
    """Re-encrypt all rows in a table column that use an old key."""
    result = await client.table(table).select(f"{pk},{column}").execute()
    rows = result.data or []

    rotated = 0
    skipped = 0
    errors = 0

    for row in rows:
        value = row[column]
        if not value:
            skipped += 1
            continue
        try:
            new_value = reencrypt_value(value)
            if new_value is None:
                skipped += 1  # already on latest key
                continue
            await client.table(table).update({column: new_value}).eq(pk, row[pk]).execute()
            rotated += 1
        except Exception as e:
            print(f"  ERROR rotating {table}.{column} row {row[pk]}: {e}")
            errors += 1

    return {"rotated": rotated, "skipped": skipped, "errors": errors}


async def main():
    print("Starting encryption key rotation...")
    client = await admin_client()

    for table, column, pk in ENCRYPTED_COLUMNS:
        print(f"\nRotating {table}.{column}...")
        stats = await rotate_table(client, table, column, pk)
        print(f"  Rotated: {stats['rotated']}, Skipped (already current): {stats['skipped']}, Errors: {stats['errors']}")

    print("\nKey rotation complete.")
    print("Next: update ENCRYPTION_KEYS to remove the old key entry.")


if __name__ == "__main__":
    asyncio.run(main())
