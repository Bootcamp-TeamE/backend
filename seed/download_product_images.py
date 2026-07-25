"""상품 이미지를 Wikimedia Commons에서 uploads/products/로 내려받는다(자체 호스팅).

외부 핫링크는 레이트리밋(429)·차단(403)이 있어, 이미지를 로컬에 받아 /uploads로 서빙한다.
멱등: 이미 받은 파일은 건너뛴다. 레이트리밋에 걸리면 다시 실행하면 실패분만 재시도.

실행: backend/ 에서
    PYTHONPATH=. ./.venv-app/bin/python seed/download_product_images.py
"""

import subprocess
import time
from pathlib import Path

from app.config import settings
from app.services.sale_generator import PRODUCT_IMAGE_DIR, PRODUCT_IMAGE_SOURCES


def main() -> None:
    dest = Path(settings.upload_dir) / PRODUCT_IMAGE_DIR
    dest.mkdir(parents=True, exist_ok=True)
    ok = skip = fail = 0
    for title, (fname, url) in PRODUCT_IMAGE_SOURCES.items():
        path = dest / fname
        if path.exists() and path.stat().st_size > 0:
            skip += 1
            continue
        code = subprocess.run(
            ["curl", "-s", "-L", "--max-time", "30", "-o", str(path), "-w", "%{http_code}", url],
            capture_output=True, text=True,
        ).stdout.strip()
        if code == "200" and path.exists() and path.stat().st_size > 0:
            ok += 1
        else:
            fail += 1
            print(f"실패 {title} http={code} {url}")
            path.unlink(missing_ok=True)
        time.sleep(0.6)  # Commons 레이트리밋(429) 회피
    print(f"이미지 다운로드: 성공 {ok}, 스킵 {skip}, 실패 {fail} (총 {len(PRODUCT_IMAGE_SOURCES)}) → {dest}")


if __name__ == "__main__":
    main()
