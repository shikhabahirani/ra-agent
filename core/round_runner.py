"""
The referee: agent A goes, then agent B goes, given whatever A produced.

Domain-agnostic on purpose - it doesn't know "Red," "Blue," "security,"
"vulnerabilities," or anything else about what the agents do, only that A
runs first and B consumes A's result. Swap in a bull-vs-bear debate pair and
this file works identically.

Whether B should even run at all is also not this file's call - the caller
supplies `should_run_b`, a predicate over A's result. This is a real gate
(the `if` below), not a prompt asking an agent to behave - the caller just
owns what the gate condition means, the same way it already owns what
`dispatch` does.

One round only, for now: A -> B, done. Looping this (A -> B -> A checks B's
work -> ...) is a one-line change to make later, not implemented here yet.
"""

from typing import Callable, TypeVar

A = TypeVar("A")
B = TypeVar("B")


def run_round(
    agent_a: Callable[[], A],
    agent_b: Callable[[A], B],
    *,
    should_run_b: Callable[[A], bool] | None = None,
    skip_message: str | None = None,
) -> tuple[A, B | None]:
    result_a = agent_a()
    if should_run_b is not None and not should_run_b(result_a):
        if skip_message:
            print(skip_message)
        return result_a, None
    result_b = agent_b(result_a)
    return result_a, result_b
