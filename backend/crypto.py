"""
AES-256-GCM encryption helpers.

Storage format (base64-encoded):  key_id:nonce_hex:ciphertext_hex
  - key_id  : identifies which key was used (for rotation)
  - nonce   : 12-byte random nonce
  - ciphertext: encrypted bytes (includes 16-byte GCM auth tag)

Key rotation:
  - Set ENCRYPTION_KEYS="v1:<base64_key1>,v2:<base64_key2>"
  - New records are encrypted with the last (latest) key.
  - Old records can be re-encrypted with the `reencrypt_value` helper.
"""

import base64
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.config import get_settings

_SEPARATOR = ":"


def _load_keys() -> dict[str, bytes]:
    """Load all available encryption keys keyed by id."""
    settings = get_settings()
    keys: dict[str, bytes] = {}

    # Multi-key format: "v1:<b64>,v2:<b64>"
    if settings.encryption_keys:
        for entry in settings.encryption_keys.split(","):
            kid, raw = entry.strip().split(":", 1)
            keys[kid.strip()] = base64.b64decode(raw.strip())

    # Single primary key always present
    if "v1" not in keys:
        keys["v1"] = base64.b64decode(settings.encryption_secret)

    return keys


def _active_key() -> tuple[str, bytes]:
    """Return the latest (active) key id and bytes."""
    keys = _load_keys()
    # Last entry is the active key
    kid = list(keys.keys())[-1]
    return kid, keys[kid]


def encrypt(plaintext: str | bytes) -> str:
    """Encrypt plaintext and return storable string: 'kid:nonce_hex:ct_hex'."""
    if isinstance(plaintext, str):
        plaintext = plaintext.encode()

    kid, key = _active_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    return _SEPARATOR.join([
        kid,
        nonce.hex(),
        ciphertext.hex(),
    ])


def decrypt(token: str) -> str:
    """Decrypt a stored token string and return plaintext."""
    parts = token.split(_SEPARATOR)
    if len(parts) != 3:
        raise ValueError("Invalid encrypted token format")

    kid, nonce_hex, ct_hex = parts
    keys = _load_keys()

    if kid not in keys:
        raise KeyError(f"Unknown encryption key id: {kid}")

    key = keys[kid]
    aesgcm = AESGCM(key)
    nonce = bytes.fromhex(nonce_hex)
    ciphertext = bytes.fromhex(ct_hex)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode()


def reencrypt_value(token: str) -> Optional[str]:
    """Re-encrypt a token with the current active key. Returns None if already current."""
    parts = token.split(_SEPARATOR)
    if len(parts) != 3:
        raise ValueError("Invalid token")

    kid = parts[0]
    active_kid, _ = _active_key()
    if kid == active_kid:
        return None  # already on latest key

    plaintext = decrypt(token)
    return encrypt(plaintext)
