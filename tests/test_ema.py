from app.ema import ema, touched


def test_ema_starts_at_first_value():
    assert ema([10, 12, 14], 2) == [10.0, 11.333333333333334, 13.11111111111111]


def test_touch_detects_crossing_in_either_direction():
    assert touched(99, 101, 100)
    assert touched(101, 99, 100)
    assert not touched(101, 102, 100)
