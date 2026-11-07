from app.bias import classify


def test_bias_boundaries_and_unknown():
    assert classify(110, {20: 105, 50: 103, 100: 101, 200: 99}) == "BULLISH"
    assert classify(90, {20: 95, 50: 97, 100: 99, 200: 101}) == "BEARISH"
    assert classify(100, {}) == "UNKNOWN"
