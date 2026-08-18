from __future__ import annotations

import hmac
from hashlib import sha256


def verify_signature(*, secret: str, body: bytes, header: str | None) -> bool:
    """Return True if X-Hub-Signature-256 matches HMAC-SHA256 of the raw body."""
    if not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header)


def sign_body(*, secret: str, body: bytes) -> str:
    """Test helper: produce a valid X-Hub-Signature-256 header value."""
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()
