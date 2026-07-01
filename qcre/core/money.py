"""Money and Rate value types.

All monetary amounts in qcre flow through :class:`Money`, which wraps
:class:`decimal.Decimal` so we never use binary floats for money. ``Rate`` is a thin
alias for ``Decimal`` used for tax rates and percentages.

Design notes
------------
* ``Money`` keeps full decimal precision internally so intermediate tax computations do
  not lose accuracy. Use :meth:`Money.round` to quantize to cents (the value posted to
  the ledger and shown to users).
* :meth:`Money.allocate` splits an amount across integer/decimal weights without losing
  or creating pennies (largest-remainder method) — essential for prorating input tax
  credits across mixed-use floor area and for allocating a purchase price.
* Rounding defaults to ``ROUND_HALF_UP`` (round half away from zero), which is the
  convention used by CRA/Revenu Québec worked examples and most accounting software.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, getcontext
from typing import Iterable, Union

# Generous precision for intermediate calculations (compound interest, IRR, etc.).
getcontext().prec = 34

Numeric = Union["Money", Decimal, int, str, float]
Rate = Decimal  # semantic alias: a proportion such as Decimal("0.09975")

_CENT = Decimal("0.01")


def to_decimal(value: Numeric) -> Decimal:
    """Coerce a supported numeric type to ``Decimal`` (floats via ``str`` to avoid noise)."""
    if isinstance(value, Money):
        return value.amount
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


class Money:
    """An immutable CAD monetary amount backed by ``Decimal``."""

    __slots__ = ("_amount",)

    def __init__(self, amount: Numeric = 0) -> None:
        object.__setattr__(self, "_amount", to_decimal(amount))

    # -- construction helpers ------------------------------------------------
    @classmethod
    def of(cls, amount: Numeric) -> "Money":
        return cls(amount)

    @classmethod
    def zero(cls) -> "Money":
        return cls(0)

    # -- accessors -----------------------------------------------------------
    @property
    def amount(self) -> Decimal:
        return self._amount

    def round(self, places: int = 2) -> "Money":
        """Quantize to *places* decimals (default cents) using ROUND_HALF_UP."""
        q = Decimal(1).scaleb(-places)
        return Money(self._amount.quantize(q, rounding=ROUND_HALF_UP))

    @property
    def cents(self) -> int:
        return int(self.round(2)._amount.scaleb(2))

    # -- arithmetic ----------------------------------------------------------
    def __add__(self, other: Numeric) -> "Money":
        return Money(self._amount + to_decimal(other))

    __radd__ = __add__

    def __sub__(self, other: Numeric) -> "Money":
        return Money(self._amount - to_decimal(other))

    def __rsub__(self, other: Numeric) -> "Money":
        return Money(to_decimal(other) - self._amount)

    def __mul__(self, factor: Numeric) -> "Money":
        return Money(self._amount * to_decimal(factor))

    __rmul__ = __mul__

    def __truediv__(self, divisor: Numeric) -> "Money":
        return Money(self._amount / to_decimal(divisor))

    def __neg__(self) -> "Money":
        return Money(-self._amount)

    def __abs__(self) -> "Money":
        return Money(abs(self._amount))

    # -- comparisons ---------------------------------------------------------
    def __eq__(self, other: object) -> bool:
        if isinstance(other, (Money, Decimal, int, str)):
            return self._amount == to_decimal(other)  # type: ignore[arg-type]
        if isinstance(other, float):
            return self.round() == Money(other).round()
        return NotImplemented

    def __lt__(self, other: Numeric) -> bool:
        return self._amount < to_decimal(other)

    def __le__(self, other: Numeric) -> bool:
        return self._amount <= to_decimal(other)

    def __gt__(self, other: Numeric) -> bool:
        return self._amount > to_decimal(other)

    def __ge__(self, other: Numeric) -> bool:
        return self._amount >= to_decimal(other)

    def __hash__(self) -> int:
        return hash(self._amount)

    def is_zero(self) -> bool:
        return self.round() == Money(0)

    def is_positive(self) -> bool:
        return self._amount > 0

    def is_negative(self) -> bool:
        return self._amount < 0

    # -- allocation ----------------------------------------------------------
    def allocate(self, weights: Iterable[Numeric]) -> list["Money"]:
        """Split this amount across *weights* so the parts sum exactly to the whole.

        Uses the largest-remainder method on cent-rounded shares. Example::

            Money("100.00").allocate([1, 1, 1])  # -> [33.34, 33.33, 33.33]
        """
        weights = [to_decimal(w) for w in weights]
        total_weight = sum(weights, Decimal(0))
        if total_weight == 0:
            raise ValueError("Cannot allocate across zero total weight")

        total_cents = self.round(2)._amount.scaleb(2).to_integral_value()
        raw = [(total_cents * w / total_weight) for w in weights]
        floored = [int(r // 1) for r in raw]
        remainder = int(total_cents) - sum(floored)
        # Hand out the leftover cents to the largest fractional remainders first.
        order = sorted(range(len(weights)), key=lambda i: raw[i] - floored[i], reverse=True)
        for i in range(remainder):
            floored[order[i % len(order)]] += 1
        return [Money(Decimal(c).scaleb(-2)) for c in floored]

    # -- representation ------------------------------------------------------
    def format(self, symbol: str = "$") -> str:
        v = self.round(2)._amount
        sign = "-" if v < 0 else ""
        whole, _, frac = f"{abs(v):.2f}".partition(".")
        groups = []
        while len(whole) > 3:
            groups.insert(0, whole[-3:])
            whole = whole[:-3]
        groups.insert(0, whole)
        return f"{sign}{symbol}{','.join(groups)}.{frac}"

    def __str__(self) -> str:
        return self.format()

    def __repr__(self) -> str:
        return f"Money('{self.round(2)._amount}')"


ZERO = Money(0)
