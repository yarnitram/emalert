from collections.abc import Iterable


def ema(values: Iterable[float], period: int) -> list[float]:
    values = [float(value) for value in values]
    if period <= 0:
        raise ValueError("period must be positive")
    if not values:
        return []
    alpha = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append((value * alpha) + (result[-1] * (1 - alpha)))
    return result


def touched(previous_price: float, price: float, level: float) -> bool:
    return (previous_price <= level <= price) or (previous_price >= level >= price) or price == level
