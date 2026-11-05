import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Annotated

from fastapi import Cookie, HTTPException, status

from app.config import get_settings

COOKIE_NAME = "a1_session"
SESSION_SECONDS = 12 * 60 * 60


def verify_password(candidate: str) -> bool:
    expected = get_settings().dashboard_password.get_secret_value()
    return hmac.compare_digest(candidate.encode(), expected.encode())


def create_session_token() -> str:
    payload = {
        "sub": "owner",
        "exp": int(time.time()) + SESSION_SECONDS,
        "nonce": secrets.token_hex(12),
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(
        get_settings().session_secret.get_secret_value().encode(), encoded, hashlib.sha256
    ).digest()
    return f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).decode()}"


def validate_session(token: str) -> bool:
    try:
        encoded_text, signature_text = token.split(".", 1)
        encoded = encoded_text.encode()
        supplied = base64.b64decode(signature_text.encode(), altchars=b"-_", validate=True)
        expected = hmac.new(
            get_settings().session_secret.get_secret_value().encode(), encoded, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(supplied, expected):
            return False
        payload = json.loads(base64.b64decode(encoded, altchars=b"-_", validate=True))
        return payload.get("sub") == "owner" and int(payload.get("exp", 0)) > time.time()
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False


def require_owner(session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None) -> str:
    if not session or not validate_session(session):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required")
    return "owner"
