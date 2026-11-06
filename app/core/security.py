import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.config import settings
from app.core.errors import DomainError

passwords = PasswordHash.recommended()
# Equalize work for unknown users without logging credentials.
DUMMY_HASH = passwords.hash(secrets.token_urlsafe(32))


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def encode_token(sub: UUID, kind: str, expiry: datetime, jti: str | None = None) -> str:
    return jwt.encode(
        {
            "sub": str(sub),
            "type": kind,
            "exp": expiry,
            "jti": jti or secrets.token_urlsafe(24),
            "iss": "internship-tracker",
            "aud": "internship-tracker-api",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_token(token: str, kind: str) -> UUID:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience="internship-tracker-api",
            issuer="internship-tracker",
            options={"require": ["exp", "sub", "type", "jti", "iss", "aud"]},
        )
        if claims["type"] != kind:
            raise ValueError
        return UUID(claims["sub"])
    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError):
        raise DomainError(401, "INVALID_TOKEN", "Invalid or expired token") from None


def token_pair(uid: UUID) -> dict[str, str]:
    now = datetime.now(UTC)
    return {
        "access_token": encode_token(
            uid, "access", now + timedelta(minutes=settings.access_token_minutes)
        ),
        "refresh_token": encode_token(
            uid, "refresh", now + timedelta(days=settings.refresh_token_days)
        ),
        "token_type": "bearer",
    }
