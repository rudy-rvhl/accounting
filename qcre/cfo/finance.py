"""Small financial-math helpers (NPV / IRR) on Decimal cash flows."""

from __future__ import annotations

from decimal import Decimal

from qcre.core.money import Money, to_decimal


def npv(rate: Decimal, cashflows: list[Money]) -> Money:
    """Net present value; ``cashflows[0]`` is time 0 (typically the negative outlay)."""
    total = Decimal(0)
    for t, cf in enumerate(cashflows):
        total += to_decimal(cf) / (Decimal(1) + rate) ** t
    return Money(total)


def irr(cashflows: list[Money], *, guess: Decimal = Decimal("0.1")) -> Decimal | None:
    """Internal rate of return via bisection. Returns ``None`` if no sign change."""
    values = [to_decimal(cf) for cf in cashflows]
    if all(v >= 0 for v in values) or all(v <= 0 for v in values):
        return None

    def f(r: Decimal) -> Decimal:
        return sum(v / (Decimal(1) + r) ** t for t, v in enumerate(values))

    low, high = Decimal("-0.9999"), Decimal("10")
    f_low, f_high = f(low), f(high)
    if f_low * f_high > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        f_mid = f(mid)
        if abs(f_mid) < Decimal("0.0001"):
            return mid
        if f_low * f_mid < 0:
            high, f_high = mid, f_mid
        else:
            low, f_low = mid, f_mid
    return (low + high) / 2
