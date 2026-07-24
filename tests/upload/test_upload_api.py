from pathlib import Path

from httpx import AsyncClient

from app.config import settings

# 1x1 PNG (최소 유효 이미지)
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f5f0000000049454e44ae426082"
)


async def test_upload_image_returns_url(client: AsyncClient):
    resp = await client.post(
        "/api/v1/uploads/images",
        files={"file": ("photo.png", _PNG, "image/png")},
    )
    assert resp.status_code == 201
    url = resp.json()["url"]
    assert url.startswith("/uploads/")

    # 실제 파일이 업로드 디렉토리에 저장됐는지 + 정리
    saved = Path(settings.upload_dir) / Path(url).name
    assert saved.exists()
    saved.unlink()


async def test_upload_rejects_non_image(client: AsyncClient):
    resp = await client.post(
        "/api/v1/uploads/images",
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 422
