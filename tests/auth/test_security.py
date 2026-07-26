import time

import jwt
import pytest

from app.config import settings
from app.core.security import create_access_token, decode_token


def test_roundtrip_encodes_sub_and_role():
    token = create_access_token(42, "owner")
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "owner"


def test_tampered_token_rejected():
    token = create_access_token(1, "user")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token + "x")


def test_expired_token_rejected(monkeypatch):
    monkeypatch.setattr(settings, "access_token_expire_minutes", -1)
    token = create_access_token(1, "user")
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token)
