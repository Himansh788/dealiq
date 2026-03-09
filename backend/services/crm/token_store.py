"""
Encrypted token storage for multi-CRM connections.
Uses Fernet (AES-128-CBC + HMAC-SHA256) for token encryption at rest.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import CRMConnection
from services.crm.base import CRMAuthTokens

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Encryption key setup
# ---------------------------------------------------------------------------
_RAW_KEY = os.getenv("CRM_TOKEN_ENCRYPTION_KEY", "")

if _RAW_KEY:
    try:
        _FERNET = Fernet(_RAW_KEY.encode() if isinstance(_RAW_KEY, str) else _RAW_KEY)
    except Exception:
        logger.warning("CRM_TOKEN_ENCRYPTION_KEY is invalid — generating ephemeral key (tokens will not survive restart)")
        _FERNET = Fernet(Fernet.generate_key())
else:
    logger.warning("CRM_TOKEN_ENCRYPTION_KEY not set — using ephemeral Fernet key (dev only, not suitable for production)")
    _FERNET = Fernet(Fernet.generate_key())


def _encrypt(plaintext: str) -> str:
    return _FERNET.encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    return _FERNET.decrypt(ciphertext.encode()).decode()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def store_tokens(
    user_id: str,
    org_id: Optional[str],
    tokens: CRMAuthTokens,
    db: AsyncSession,
) -> None:
    """Upsert encrypted CRM tokens for a user/org/provider combination."""
    # Serialize the `extra` dict (e.g. instance_url for Salesforce) as JSON
    # and store it in the instance_url column which is used for generic extras.
    extra_json = json.dumps(tokens.extra) if tokens.extra else "{}"

    # Check for existing record
    stmt = select(CRMConnection).where(
        CRMConnection.user_id == user_id,
        CRMConnection.provider == tokens.provider,
    )
    if org_id:
        stmt = stmt.where(CRMConnection.org_id == org_id)

    result = await db.execute(stmt)
    existing: Optional[CRMConnection] = result.scalar_one_or_none()

    if existing:
        existing.access_token_encrypted = _encrypt(tokens.access_token)
        existing.refresh_token_encrypted = _encrypt(tokens.refresh_token)
        existing.token_expires_at = tokens.expires_at
        existing.instance_url = extra_json
        existing.is_active = True
        existing.sync_status = "idle"
        existing.sync_error = None
    else:
        conn = CRMConnection(
            user_id=user_id,
            org_id=org_id,
            provider=tokens.provider,
            access_token_encrypted=_encrypt(tokens.access_token),
            refresh_token_encrypted=_encrypt(tokens.refresh_token),
            token_expires_at=tokens.expires_at,
            instance_url=extra_json,
            is_active=True,
        )
        db.add(conn)

    await db.commit()


async def get_tokens(
    user_id: str,
    org_id: Optional[str],
    provider: str,
    db: AsyncSession,
) -> Optional[CRMAuthTokens]:
    """Retrieve and decrypt CRM tokens. Returns None if not found or decryption fails."""
    stmt = select(CRMConnection).where(
        CRMConnection.user_id == user_id,
        CRMConnection.provider == provider,
        CRMConnection.is_active == True,  # noqa: E712
    )
    if org_id:
        stmt = stmt.where(CRMConnection.org_id == org_id)

    result = await db.execute(stmt)
    conn: Optional[CRMConnection] = result.scalar_one_or_none()

    if not conn:
        return None

    try:
        access_token = _decrypt(conn.access_token_encrypted)
        refresh_token = _decrypt(conn.refresh_token_encrypted)
    except InvalidToken:
        logger.error("Failed to decrypt tokens for user=%s provider=%s — token data corrupted", user_id, provider)
        return None

    # Deserialize extra JSON from instance_url column
    extra: dict = {}
    if conn.instance_url:
        try:
            extra = json.loads(conn.instance_url)
        except (json.JSONDecodeError, TypeError):
            # Fallback: treat as plain URL string (legacy rows)
            extra = {"instance_url": conn.instance_url}

    expires_at = conn.token_expires_at or datetime.now(timezone.utc)

    return CRMAuthTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        provider=provider,
        extra=extra,
    )


async def delete_tokens(
    user_id: str,
    org_id: Optional[str],
    provider: str,
    db: AsyncSession,
) -> None:
    """Hard-delete CRM connection tokens for a user/org/provider."""
    stmt = delete(CRMConnection).where(
        CRMConnection.user_id == user_id,
        CRMConnection.provider == provider,
    )
    if org_id:
        stmt = stmt.where(CRMConnection.org_id == org_id)

    await db.execute(stmt)
    await db.commit()
