import asyncio

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sale import Sale, SaleStatus
from tests.order.helpers import seed_sale, seed_user


async def test_no_oversell_under_concurrency(client: AsyncClient, session: AsyncSession):
    """재고 5개에 20건 동시 예약 → 정확히 5건만 성공, 재고 음수 없음."""
    sale = await seed_sale(session, remaining=5, sale_price=2000)
    user = await seed_user(session)

    async def reserve():
        return await client.post(
            "/api/v1/orders", json={"user_id": user.id, "sale_id": sale.id, "quantity": 1}
        )

    responses = await asyncio.gather(*[reserve() for _ in range(20)])
    codes = [r.status_code for r in responses]

    assert codes.count(201) == 5
    assert codes.count(409) == 15

    fresh = await session.get(Sale, sale.id)
    await session.refresh(fresh)
    assert fresh.remaining_quantity == 0
    assert fresh.status == SaleStatus.SOLDOUT
