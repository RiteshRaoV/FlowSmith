from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Step:
    """
    Represents a registered step within a Flow.

    name:    Unique identifier within the flow. Used as the DB key for
             node records and as the ctx.data key for the step's output.
    fn:      The callable to execute. Signature: (ctx: Context) -> dict
    retries: Total number of attempts (including the first). Default 1 = no retry.
    """
    name: str
    fn: Callable
    retries: int = 1

    def __post_init__(self):
        if self.retries < 1:
            raise ValueError(f"Step '{self.name}': retries must be >= 1 (got {self.retries})")
