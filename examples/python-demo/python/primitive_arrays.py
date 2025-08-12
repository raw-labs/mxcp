"""Example showing Python endpoints can return primitive arrays."""


def show_primitive_arrays() -> list:
    """Return Fibonacci sequence as array of numbers."""
    return [1, 1, 2, 3, 5, 8, 13, 21, 34, 55]


def get_languages() -> list:
    """Return list of programming languages."""
    return ["Python", "JavaScript", "Go", "Rust", "TypeScript"]


def get_pi_digits() -> list:
    """Return digits of pi."""
    return [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5, 8, 9, 7, 9]
