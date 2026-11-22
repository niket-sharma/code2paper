from decimal import Decimal

import pytest

from c2p.common import C2PError, eval_formula, formula_ids, rounds_to, shown_decimals, to_decimal


@pytest.mark.parametrize(
    "ev,paper,expected",
    [
        ("0.9123", "0.912", "rounding"),
        ("0.9125", "0.913", "rounding"),  # half-up
        ("0.9125", "0.912", "rounding"),  # half-even
        ("0.912", "0.912", "exact"),
        ("0.9120", "0.912", "exact"),
        ("2.4410", "2.45", None),
        ("2.4410", "2.4", "rounding"),
        ("12544", "12544", "exact"),
        ("1e-4", "0.0001", "exact"),
    ],
)
def test_rounds_to(ev: str, paper: str, expected: str | None) -> None:
    assert rounds_to(Decimal(ev), paper) == expected


def test_shown_decimals_and_parse() -> None:
    assert shown_decimals("2.310") == 3
    assert shown_decimals("12") == 0
    assert to_decimal("1,200") == Decimal(1200)
    assert to_decimal("abc") is None


def test_eval_formula() -> None:
    vals = {"E0001": Decimal("2.8731"), "E0002": Decimal("2.3142")}
    got = eval_formula("(E0001 - E0002) / E0001 * 100", vals)
    assert abs(got - Decimal("19.4528")) < Decimal("0.001")
    assert formula_ids("mean(E0001, E0002) - E0002") == {"E0001", "E0002"}
    with pytest.raises(C2PError):
        eval_formula("__import__('os')", vals)
    with pytest.raises(C2PError):
        eval_formula("E0003 + 1", vals)
