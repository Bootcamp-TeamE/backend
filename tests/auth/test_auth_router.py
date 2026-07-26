from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import Role, User
from app.services import google_auth
from tests.conftest import auth_headers


def _fake_google(monkeypatch, sub, email, name="구글유저"):
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda *a, **k: {"sub": sub, "email": email, "name": name},
    )


async def test_google_login_creates_user(client: AsyncClient, monkeypatch):
    _fake_google(monkeypatch, "g-1", "new@t.local")
    resp = await client.post("/api/v1/auth/google", json={"id_token": "x"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["email"] == "new@t.local"
    assert body["user"]["role"] == "user"


async def test_google_login_is_idempotent_by_sub(client: AsyncClient, monkeypatch):
    _fake_google(monkeypatch, "g-2", "same@t.local")
    first = (await client.post("/api/v1/auth/google", json={"id_token": "x"})).json()
    second = (await client.post("/api/v1/auth/google", json={"id_token": "x"})).json()
    assert first["user"]["id"] == second["user"]["id"]


async def test_google_login_rejects_invalid_token(client: AsyncClient, monkeypatch):
    def boom(*a, **k):
        raise ValueError("bad")

    monkeypatch.setattr(google_auth.google_id_token, "verify_oauth2_token", boom)
    resp = await client.post("/api/v1/auth/google", json={"id_token": "x"})
    assert resp.status_code == 401


async def test_google_login_missing_email_401(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda *a, **k: {"sub": "g-noemail", "email": None, "name": "x"},
    )
    resp = await client.post("/api/v1/auth/google", json={"id_token": "x"})
    assert resp.status_code == 401


async def test_email_conflict_with_other_sub_409(client: AsyncClient, session: AsyncSession, monkeypatch):
    session.add(User(email="dup@t.local", google_sub="existing-sub", role=Role.USER))
    await session.commit()
    _fake_google(monkeypatch, "different-sub", "dup@t.local")
    resp = await client.post("/api/v1/auth/google", json={"id_token": "x"})
    assert resp.status_code == 409


async def test_me_returns_current_user(client: AsyncClient, session: AsyncSession):
    user = User(email="me@t.local", google_sub="sub-me", role=Role.USER)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    resp = await client.get("/api/v1/auth/me", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json()["id"] == user.id


async def test_me_without_token_401(client: AsyncClient):
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_dev_login_demo_buyer_seeded(client: AsyncClient, session: AsyncSession, monkeypatch):
    monkeypatch.setattr(settings, "dev_login", True)
    user = User(email="buyer@solde.demo", google_sub="demo:buyer", role=Role.USER)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    resp = await client.post("/api/v1/auth/dev-login", json={"email": "buyer@solde.demo"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["id"] == user.id
    assert body["user"]["email"] == "buyer@solde.demo"


async def test_dev_login_rejects_non_whitelisted_email(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "dev_login", True)

    resp = await client.post("/api/v1/auth/dev-login", json={"email": "stranger@evil.com"})

    assert resp.status_code == 403


async def test_dev_login_whitelisted_but_not_seeded_404(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "dev_login", True)

    resp = await client.post("/api/v1/auth/dev-login", json={"email": "buyer@solde.demo"})

    assert resp.status_code == 404


async def test_dev_login_disabled_by_default_404(client: AsyncClient):
    resp = await client.post("/api/v1/auth/dev-login", json={"email": "buyer@solde.demo"})

    assert resp.status_code == 404
