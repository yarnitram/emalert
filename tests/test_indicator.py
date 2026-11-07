from decimal import Decimal

from app.indicator import ClosedEMA


def test_provisional_prices_do_not_change_the_closed_ema():
    indicator = ClosedEMA(3)
    indicator.close(Decimal(8))
    indicator.close(Decimal(10))
    assert indicator.preview(Decimal(20)) is None
    indicator.close(Decimal(12))
    assert indicator.preview(Decimal(20)) == 15
    assert indicator.preview(Decimal(16)) == 13
    assert indicator.value == 10
    indicator.close(Decimal(16))
    assert indicator.value == 13
