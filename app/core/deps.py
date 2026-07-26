import jwt
from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.security import decode_token
from app.database import get_session
from app.models.user import Role, User


async def _user_from_token(token: str, session: AsyncSession) -> User:
    try:
        payload = decode_token(token)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=errors.INVALID_TOKEN) from exc
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=errors.INVALID_TOKEN)
    return user


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=errors.NOT_AUTHENTICATED)
    return await _user_from_token(authorization[len("Bearer ") :], session)


async def get_current_owner(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=errors.OWNER_ONLY)
    return user


async def get_user_from_query_token(
    token: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> User:
    return await _user_from_token(token, session)
