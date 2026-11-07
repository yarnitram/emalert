from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app.touch import TouchState


def test_touch_rearms_after_cooldown_and_distance():
    state = TouchState(cooldown=timedelta(seconds=10))
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert not state.observe(Decimal("99"), Decimal("100"), t0)
    assert state.observe(Decimal("100"), Decimal("100"), t0 + timedelta(seconds=1))
    assert not state.observe(Decimal("100"), Decimal("100"), t0 + timedelta(seconds=20))
    assert not state.observe(Decimal("101"), Decimal("100"), t0 + timedelta(seconds=21))
    assert state.observe(Decimal("100"), Decimal("100"), t0 + timedelta(seconds=22))
