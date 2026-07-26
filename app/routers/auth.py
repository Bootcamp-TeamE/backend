from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.deps import get_current_user
from app.core.security import create_access_token
from app.config import settings
from app.database import get_session
from app.models.user import Role, User
from app.schemas.auth import DevLoginRequest, GoogleLoginRequest, TokenResponse, UserResponse
from app.services.google_auth import GoogleTokenError, verify_google_id_token

router = APIRouter(prefix="/auth", tags=["인증"])


async def _get_by_email(session: AsyncSession, email: str | None) -> User | None:
    if not email:
        return None
    return (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()


def _token_response(user: User) -> TokenResponse:
    token = create_access_token(user.id, user.role.value)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/google", response_model=TokenResponse, summary="구글 로그인")
async def google_login(
    payload: GoogleLoginRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    try:
        info = verify_google_id_token(payload.id_token)
    except GoogleTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=errors.INVALID_TOKEN)
    if not info["email"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=errors.INVALID_TOKEN)

    user = (
        await session.execute(select(User).where(User.google_sub == info["sub"]))
    ).scalar_one_or_none()
    if user is None:
        # 같은 이메일이 다른 google_sub로 이미 있으면 병합하지 않고 거부.
        if await _get_by_email(session, info["email"]) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=errors.EMAIL_ALREADY_REGISTERED)
        user = User(email=info["email"], google_sub=info["sub"], name=info["name"], role=Role.USER)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return _token_response(user)


@router.get("/me", response_model=UserResponse, summary="내 정보")
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/dev-login", response_model=TokenResponse, summary="개발용 로그인(구글 없이)")
async def dev_login(
    payload: DevLoginRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    if not settings.dev_login:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.FORBIDDEN)
    user = await _get_by_email(session, payload.email)
    if user is None:
        user = User(
            email=payload.email, google_sub=f"dev:{payload.email}", name=payload.name, role=Role.USER
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return _token_response(user)
