from collections.abc import Callable
from dataclasses import dataclass

BACKOFF_STRATEGIES = ("fixed", "exponential", "jitter")


@dataclass
class Step:
    """
    Represents a registered step within a Flow.

    name:         Unique identifier within the flow. Used as the DB key and
                  ctx.data key for the step's output.
    fn:           Callable with signature (ctx: Context) -> dict
    retries:      Total attempts including the first. retries=3 means the step
                  will be tried up to 3 times before raising StepFailed.
    backoff:      Delay strategy between retries.
                    "fixed"       — constant delay of backoff_base seconds
                    "exponential" — backoff_base * 2^(attempt-1) seconds
                    "jitter"      — exponential + random jitter (avoids thundering herd)
    backoff_base: Base delay in seconds. Default 0.0 (no delay).
    timeout:      Max seconds a single attempt may run before StepTimeoutError
                  is raised. None means no timeout.
    """
    name: str
    fn: Callable
    retries: int = 1
    backoff: str = "fixed"
    backoff_base: float = 0.0
    timeout: int | None = None

    def __post_init__(self):
        if self.retries < 1:
            raise ValueError(
                f"Step '{self.name}': retries must be >= 1 (got {self.retries})"
            )
        if self.backoff not in BACKOFF_STRATEGIES:
            raise ValueError(
                f"Step '{self.name}': backoff must be one of {BACKOFF_STRATEGIES} "
                f"(got '{self.backoff}')"
            )
        if self.backoff_base < 0:
            raise ValueError(
                f"Step '{self.name}': backoff_base must be >= 0 (got {self.backoff_base})"
            )
        if self.timeout is not None and self.timeout < 1:
            raise ValueError(
                f"Step '{self.name}': timeout must be >= 1 second (got {self.timeout})"
            )

