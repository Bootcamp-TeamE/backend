import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.config import settings

router = APIRouter(prefix="/uploads", tags=["업로드"])

# 이미지 MIME → 확장자. 이 목록에 없으면 거절한다.
_ALLOWED = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_BYTES = 5 * 1024 * 1024  # 5MB


@router.post("/images", status_code=status.HTTP_201_CREATED, summary="상품 이미지 업로드")
async def upload_image(file: UploadFile = File(...)) -> dict:
    ext = _ALLOWED.get(file.content_type or "")
    if ext is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="이미지 파일만 업로드할 수 있습니다"
        )
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="파일이 너무 큽니다(최대 5MB)")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    (upload_dir / name).write_bytes(data)
    return {"url": f"/uploads/{name}"}
