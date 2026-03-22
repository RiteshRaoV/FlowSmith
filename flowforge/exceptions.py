class FlowForgeNotConfigured(Exception):
    """
    Raised when a Flow is created before flowforge.configure() has been called.
    """
    def __init__(self):
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
    def __init__(self, step_name: str, attempt: int, original: Exception):
        self.step_name = step_name
        self.attempt = attempt
        self.original = original
        super().__init__(
            f"Step '{step_name}' failed after {attempt} attempt(s): {original}"
        )


class FlowAlreadyCompleted(Exception):
    """
    Raised when flow.run() is called with a tracking_id that already
    belongs to a COMPLETED flow.
    """
    def __init__(self, tracking_id: str):
        super().__init__(
            f"Flow with tracking_id='{tracking_id}' is already COMPLETED. "
            "Use a new tracking_id to start a fresh execution."
        )
