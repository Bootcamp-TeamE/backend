from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category


async def test_list_categories_active_sorted(client: AsyncClient, session: AsyncSession):
    session.add_all([
        Category(code="butcher", name_ko="정육", sort_order=1, default_unit_code="geun"),
        Category(code="flower", name_ko="화훼", sort_order=9, default_unit_code="songi"),
        Category(code="hidden", name_ko="비활성", sort_order=5, default_unit_code="piece", is_active=False),
    ])
    await session.commit()

    resp = await client.get("/api/v1/categories")
    assert resp.status_code == 200
    codes = [c["code"] for c in resp.json()]
    assert codes == ["butcher", "flower"]  # sort_order 순, 비활성 제외
    assert resp.json()[0]["name_ko"] == "정육"
    assert resp.json()[0]["default_unit_code"] == "geun"
