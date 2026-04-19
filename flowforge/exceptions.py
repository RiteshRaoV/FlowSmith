class FlowForgeNotConfigured(Exception):
    """
    Raised when a Flow is created before flowforge.configure() has been called.
    """
    def __init__(self) -> None:
        super().__init__(
            "FlowForge is not configured. "
            "Call flowforge.configure(database_url=...) at server startup "
            "before creating any Flow instances."
        )


class StepFailed(Exception):
    """
    Raised when a step exhausts all retry attempts.
    Wraps the original exception for inspection.
    """
    def __init__(self, step_name: str, attempt: int, original: Exception) -> None:
        self.step_name = step_name
        self.attempt = attempt
        self.original = original
        super().__init__(
            f"Step '{step_name}' failed after {attempt} attempt(s): {original}"
        )


class StepTimeoutError(Exception):
    """
    Raised when a step exceeds its configured timeout.
    Treated as a retryable failure — the step will be retried
    if attempts remain, with backoff applied.
    """
    def __init__(self, step_name: str, timeout: int, attempt: int) -> None:
        self.step_name = step_name
        self.timeout = timeout
        self.attempt = attempt
        super().__init__(
            f"Step '{step_name}' timed out after {timeout}s "
            f"(attempt {attempt})"
        )


class FlowAlreadyCompleted(Exception):
    """
    Raised when flow.run() is called with a tracking_id that already
    belongs to a COMPLETED flow.
    """
    def __init__(self, tracking_id: str) -> None:
        super().__init__(
            f"Flow with tracking_id='{tracking_id}' is already COMPLETED. "
            "Use a new tracking_id to start a fresh execution."
        )
