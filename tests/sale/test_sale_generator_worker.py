"""세일 생성 워커의 스케줄 계산(next_slot) 검증 — 하루 종일 짝수 시(정각) 2시간 간격."""

from datetime import datetime

from zoneinfo import ZoneInfo

from app.workers.sale_generator_worker import KST, SLOTS, next_slot


def _kst(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=ZoneInfo("Asia/Seoul"))


def test_next_even_hour_slot():
    assert next_slot(_kst(2026, 7, 25, 6, 30)) == _kst(2026, 7, 25, 8, 0)
    assert next_slot(_kst(2026, 7, 25, 9, 30)) == _kst(2026, 7, 25, 10, 0)
    assert next_slot(_kst(2026, 7, 25, 0, 30)) == _kst(2026, 7, 25, 2, 0)
    assert next_slot(_kst(2026, 7, 25, 14, 1)) == _kst(2026, 7, 25, 16, 0)


def test_exactly_on_slot_returns_following_slot():
    assert next_slot(_kst(2026, 7, 25, 10, 0)) == _kst(2026, 7, 25, 12, 0)


def test_after_last_slot_wraps_to_next_day_midnight():
    assert next_slot(_kst(2026, 7, 25, 22, 0)) == _kst(2026, 7, 26, 0, 0)
    assert next_slot(_kst(2026, 7, 25, 23, 30)) == _kst(2026, 7, 26, 0, 0)


def test_slots_are_all_day_two_hour_steps():
    assert SLOTS == list(range(0, 24, 2))
    assert len(SLOTS) == 12
    assert KST.key == "Asia/Seoul"
