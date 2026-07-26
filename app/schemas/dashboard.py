from pydantic import BaseModel


class DashboardResponse(BaseModel):
    owner_id: int
    store_id: int
    active_sales: int      # 활성 세일 수
    today_orders: int      # 오늘 판매(결제) 건수
    today_revenue: int     # 손실 회수액(오늘 결제액 합)
    total_reach: int       # 누적 알림 도달
