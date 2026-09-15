"""Domain-specific exceptions."""


class CalculationError(Exception):
    """Base class for calculator domain errors."""


class DivisionByZeroError(CalculationError):
    """Raised when division by zero is requested."""


class UnknownOperationError(CalculationError):
    """Raised when an operation is not registered."""
