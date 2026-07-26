import pytest

from app.services import google_auth


def test_verify_returns_identity(monkeypatch):
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda token, request, audience: {"sub": "g-123", "email": "a@b.com", "name": "홍길동"},
    )
    out = google_auth.verify_google_id_token("dummy")
    assert out == {"sub": "g-123", "email": "a@b.com", "name": "홍길동"}


def test_invalid_token_raises(monkeypatch):
    def boom(token, request, audience):
        raise ValueError("bad audience")

    monkeypatch.setattr(google_auth.google_id_token, "verify_oauth2_token", boom)
    with pytest.raises(google_auth.GoogleTokenError):
        google_auth.verify_google_id_token("dummy")
