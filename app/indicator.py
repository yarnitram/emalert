from decimal import Decimal


class ClosedEMA:
    """Seed from closed candles and preview without mutating the seed."""

    def __init__(self, period: int):
        if period < 1:
            raise ValueError("period must be positive")
        self.period = period
        self.alpha = Decimal(2) / (period + 1)
        self.value: Decimal | None = None
        self._count = 0
        self._sum = Decimal(0)

    def preview(self, price: Decimal) -> Decimal | None:
        if self.value is None:
            return None
        return self.value + self.alpha * (price - self.value)

    def close(self, price: Decimal) -> None:
        if self.value is not None:
            self.value = self.preview(price)
            return
        self._sum += price
        self._count += 1
        if self._count == self.period:
            self.value = self._sum / self.period
