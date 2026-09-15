"""Command-line adapter for the calculator domain."""

import argparse
from decimal import Decimal

from .application import Calculator
from .errors import CalculationError


def _format(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f") if normalized == normalized.to_integral() else str(normalized)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Perform a precise arithmetic calculation.")
    parser.add_argument("left", help="Left operand")
    parser.add_argument("operation", help="add, subtract, multiply, divide, or a symbol")
    parser.add_argument("right", help="Right operand")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        print(_format(Calculator().calculate(args.left, args.operation, args.right)))
    except CalculationError as exc:
        print(f"error: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
