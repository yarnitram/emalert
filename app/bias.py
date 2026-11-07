def classify(price: float, emas: dict[int, float]) -> str:
    required = [20, 50, 100, 200]
    if any(length not in emas for length in required):
        return "UNKNOWN"
    e20, e50, e100, e200 = (emas[n] for n in required)
    if price > e20 > e50 > e100 > e200:
        return "BULLISH"
    if price < e20 < e50 < e100 < e200:
        return "BEARISH"
    if price > e100 and price > e200:
        return "RANGE_BULLISH"
    if price < e100 and price < e200:
        return "RANGE_BEARISH"
    return "RANGE_NEUTRAL"
