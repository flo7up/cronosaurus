"""
Encryption helpers for securing sensitive data (e.g. SMTP passwords) at rest.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256) from the
`cryptography` library.  The encryption key is derived from a secret
configured via the EMAIL_ENCRYPTION_KEY environment variable.

If no key is configured, a deterministic one is derived from the Cosmos DB
key so that the app still works out-of-the-box — but operators **should**
set a dedicated EMAIL_ENCRYPTION_KEY for production use.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet

from app.config import settings

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Lazily create and cache the Fernet instance."""
    global _fernet
    if _fernet is not None:
        return _fernet

    raw_key = settings.email_encryption_key
    if not raw_key:
        # Derive a key from the Cosmos DB key as a fallback
        if not settings.cosmos_key:
            raise RuntimeError(
                "Neither EMAIL_ENCRYPTION_KEY nor COSMOS_KEY is set. "
                "Please set EMAIL_ENCRYPTION_KEY in your .env file."
            )
        raw_key = settings.cosmos_key
        logger.warning(
            "EMAIL_ENCRYPTION_KEY not set — deriving encryption key from COSMOS_KEY. "
            "Set a dedicated EMAIL_ENCRYPTION_KEY for production."
        )

    # Fernet requires a 32-byte url-safe base64-encoded key.
    # We derive it deterministically from the raw secret via SHA-256.
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    _fernet = Fernet(key)
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns a base64-encoded ciphertext string."""
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """Decrypt a ciphertext string produced by `encrypt()`."""
    if not ciphertext:
        return ""
    return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
