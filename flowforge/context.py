from copy import deepcopy
from typing import Any, Dict


class Context:
    """
    Carries shared state between steps within a single flow execution.

    Step outputs are stored here automatically by the executor after
    each successful step. Downstream steps access them via ctx.data.

    Example:
        def charge_payment(ctx):
            return {"payment_id": "pay_123"}

        def create_order(ctx):
            pid = ctx.data["charge_payment"]["payment_id"]  # set by executor
            ...
    """

    def __init__(self, data: Dict[str, Any] = None):
        self.data: Dict[str, Any] = deepcopy(data or {})

    def store(self, step_name: str, output: Dict[str, Any]) -> None:
        """Called by the executor to store a step's output under its name."""
        self.data[step_name] = deepcopy(output)

    def snapshot(self) -> Dict[str, Any]:
        """Return a deep copy of the current data dict for persistence."""
        return deepcopy(self.data)

    def __repr__(self) -> str:
        keys = list(self.data.keys())
        return f"Context(keys={keys})"
