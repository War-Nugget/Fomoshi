"""Money helpers.

All money is stored as integer *micros* (millionths of a dollar) so there are no
floating-point rounding errors. Kalshi quotes prices as dollar strings with up to
six decimals ("0.4200"), which map exactly onto micros.
"""

from decimal import ROUND_HALF_UP, Decimal

MICROS = 1_000_000  # $1.00, also the payout of a winning contract


def to_micros(value: str | float | int | Decimal | None) -> int | None:
    if value is None or value == "":
        return None
    d = Decimal(str(value)) * MICROS
    return int(d.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def to_dollars(micros: int | None) -> float | None:
    if micros is None:
        return None
    return round(micros / MICROS, 6)


def to_contracts(value: str | float | int | None) -> int:
    """Kalshi sends contract counts as fixed-point strings ("13.00"). We trade whole contracts."""
    if value is None or value == "":
        return 0
    return int(Decimal(str(value)))
