from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.user import Role, User
from tests.conftest import auth_headers


async def _seed(session: AsyncSession) -> User:
    session.add_all([
        Category(code="butcher", name_ko="정육", sort_order=1, default_unit_code="geun"),
        Category(code="seafood", name_ko="수산", sort_order=2, default_unit_code="kg"),
    ])
    user = User(email="sub@test.local", google_sub="sub-1", role=Role.USER)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _body(**over) -> dict:
    b = {
        "categories": ["butcher"],
        "lat": 37.58,
        "lng": 127.04,
        "min_discount_rate": 30,
        "max_price": 20000,
        "radius_m": 2000,
    }
    b.update(over)
    return b


async def test_create_subscription(client: AsyncClient, session: AsyncSession):
    user = await _seed(session)
    resp = await client.post("/api/v1/subscriptions", json=_body(), headers=auth_headers(user))
    assert resp.status_code == 201
    body = resp.json()
    assert body["categories"] == ["butcher"]
    assert body["min_discount_rate"] == 30
    assert body["radius_m"] == 2000
    assert body["push_enabled"] is True
    assert body["opted_out"] is False


async def test_create_subscription_defaults(client: AsyncClient, session: AsyncSession):
    user = await _seed(session)
    resp = await client.post(
        "/api/v1/subscriptions",
        json={"categories": ["butcher"], "lat": 37.58, "lng": 127.04},
        headers=auth_headers(user),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["radius_m"] == 1000  # 기본 1km
    assert body["min_discount_rate"] == 0
    assert body["max_price"] is None


async def test_create_subscription_unknown_category(client: AsyncClient, session: AsyncSession):
    user = await _seed(session)
    resp = await client.post(
        "/api/v1/subscriptions",
        json=_body(categories=["butcher", "없음"]),
        headers=auth_headers(user),
    )
    assert resp.status_code == 422


async def test_create_subscription_invalid_discount_rate(client: AsyncClient, session: AsyncSession):
    user = await _seed(session)
    resp = await client.post(
        "/api/v1/subscriptions", json=_body(min_discount_rate=150), headers=auth_headers(user)
    )
    assert resp.status_code == 422


async def test_create_subscription_invalid_receive_window(client: AsyncClient, session: AsyncSession):
    user = await _seed(session)
    resp = await client.post(
        "/api/v1/subscriptions",
        json=_body(receive_from=20, receive_to=8),
        headers=auth_headers(user),
    )
    assert resp.status_code == 422


async def test_list_subscriptions_by_user(client: AsyncClient, session: AsyncSession):
    user = await _seed(session)
    other = User(email="other@test.local", google_sub="sub-2", role=Role.USER)
    session.add(other)
    await session.commit()
    await session.refresh(other)

    await client.post(
        "/api/v1/subscriptions", json=_body(categories=["butcher"]), headers=auth_headers(user)
    )
    await client.post(
        "/api/v1/subscriptions", json=_body(categories=["seafood"]), headers=auth_headers(user)
    )
    await client.post("/api/v1/subscriptions", json=_body(), headers=auth_headers(other))

    resp = await client.get("/api/v1/subscriptions", headers=auth_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2  # 유저당 여러 개 허용, 남의 구독 제외
    assert {tuple(s["categories"]) for s in body} == {("butcher",), ("seafood",)}


async def test_update_subscription(client: AsyncClient, session: AsyncSession):
    user = await _seed(session)
    sub_id = (
        await client.post("/api/v1/subscriptions", json=_body(), headers=auth_headers(user))
    ).json()["id"]
    resp = await client.patch(
        f"/api/v1/subscriptions/{sub_id}",
        json={"min_discount_rate": 50, "push_enabled": False},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["min_discount_rate"] == 50
    assert resp.json()["push_enabled"] is False


async def test_update_subscription_opt_out(client: AsyncClient, session: AsyncSession):
    user = await _seed(session)
    sub_id = (
        await client.post("/api/v1/subscriptions", json=_body(), headers=auth_headers(user))
    ).json()["id"]
    resp = await client.patch(
        f"/api/v1/subscriptions/{sub_id}", json={"opted_out": True}, headers=auth_headers(user)
    )
    assert resp.status_code == 200
    assert resp.json()["opted_out"] is True


async def test_update_subscription_not_found(client: AsyncClient, session: AsyncSession):
    user = await _seed(session)
    resp = await client.patch(
        "/api/v1/subscriptions/99999999", json={"opted_out": True}, headers=auth_headers(user)
    )
    assert resp.status_code == 404


async def test_delete_subscription(client: AsyncClient, session: AsyncSession):
    user = await _seed(session)
    sub_id = (
        await client.post("/api/v1/subscriptions", json=_body(), headers=auth_headers(user))
    ).json()["id"]
    resp = await client.delete(f"/api/v1/subscriptions/{sub_id}", headers=auth_headers(user))
    assert resp.status_code == 204
    listed = await client.get("/api/v1/subscriptions", headers=auth_headers(user))
    assert listed.json() == []  # 삭제 후 목록에서 사라진다


async def test_delete_subscription_not_found(client: AsyncClient, session: AsyncSession):
    user = await _seed(session)
    resp = await client.delete("/api/v1/subscriptions/99999999", headers=auth_headers(user))
    assert resp.status_code == 404


async def test_delete_subscription_idempotent(client: AsyncClient, session: AsyncSession):
    user = await _seed(session)
    sub_id = (
        await client.post("/api/v1/subscriptions", json=_body(), headers=auth_headers(user))
    ).json()["id"]
    assert (
        await client.delete(f"/api/v1/subscriptions/{sub_id}", headers=auth_headers(user))
    ).status_code == 204
    assert (
        await client.delete(f"/api/v1/subscriptions/{sub_id}", headers=auth_headers(user))
    ).status_code == 404  # 재삭제 no-op
