"""Operation strategies and their registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal

from .errors import DivisionByZeroError, UnknownOperationError


class Operation(ABC):
    """Strategy interface for a binary calculation."""

    symbol: str

    @abstractmethod
    def execute(self, left: Decimal, right: Decimal) -> Decimal:
        """Return the result of applying the operation."""


class Add(Operation):
    symbol = "+"

    def execute(self, left: Decimal, right: Decimal) -> Decimal:
        return left + right


class Subtract(Operation):
    symbol = "-"

    def execute(self, left: Decimal, right: Decimal) -> Decimal:
        return left - right


class Multiply(Operation):
    symbol = "*"

    def execute(self, left: Decimal, right: Decimal) -> Decimal:
        return left * right


class Divide(Operation):
    symbol = "/"

    def execute(self, left: Decimal, right: Decimal) -> Decimal:
        if right == 0:
            raise DivisionByZeroError("Cannot divide by zero")
        return left / right


@dataclass
class OperationRegistry:
    """Registry/factory that resolves strategies by symbol or name."""

    _operations: dict[str, Operation] = field(default_factory=dict)

    def register(self, name: str, operation: Operation, *aliases: str) -> None:
        for key in (name, operation.symbol, *aliases):
            self._operations[key.lower()] = operation

    def resolve(self, key: str) -> Operation:
        try:
            return self._operations[key.lower()]
        except KeyError as exc:
            raise UnknownOperationError(f"Unknown operation: {key}") from exc

    @classmethod
    def with_defaults(cls) -> "OperationRegistry":
        registry = cls()
        registry.register("add", Add(), "plus")
        registry.register("subtract", Subtract(), "minus")
        registry.register("multiply", Multiply(), "times", "x")
        registry.register("divide", Divide())
        return registry
