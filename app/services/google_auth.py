from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.config import settings


class GoogleTokenError(Exception):
    """구글 ID 토큰 검증 실패."""


def verify_google_id_token(id_token: str) -> dict:
    try:
        info = google_id_token.verify_oauth2_token(
            id_token, google_requests.Request(), settings.google_client_id
        )
    except ValueError as exc:  # 서명·aud·만료 등 모든 검증 실패는 ValueError
        raise GoogleTokenError(str(exc)) from exc
    return {"sub": info["sub"], "email": info.get("email"), "name": info.get("name")}
