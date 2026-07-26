import pytest
from fastapi import HTTPException

from app.core.deps import get_current_owner, get_current_user
from app.core.security import create_access_token
from app.models.user import Role, User


async def _add_user(session, role=Role.USER) -> User:
    user = User(email=f"{role.value}@t.local", google_sub=f"sub-{role.value}", role=role)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_get_current_user_from_bearer(session):
    user = await _add_user(session)
    got = await get_current_user(f"Bearer {create_access_token(user.id, 'user')}", session)
    assert got.id == user.id


async def test_missing_header_401(session):
    with pytest.raises(HTTPException) as e:
        await get_current_user(None, session)
    assert e.value.status_code == 401


async def test_bad_token_401(session):
    with pytest.raises(HTTPException) as e:
        await get_current_user("Bearer garbage", session)
    assert e.value.status_code == 401


async def test_owner_guard_rejects_plain_user(session):
    user = await _add_user(session, Role.USER)
    with pytest.raises(HTTPException) as e:
        await get_current_owner(user)
    assert e.value.status_code == 403


async def test_owner_guard_allows_owner(session):
    owner = await _add_user(session, Role.OWNER)
    assert (await get_current_owner(owner)).id == owner.id
