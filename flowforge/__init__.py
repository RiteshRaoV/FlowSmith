"""
FlowForge — lightweight durable workflow execution for Python backends.

Quickstart:
    import flowforge

    # Once at server startup
    flowforge.configure(database_url=os.environ["DATABASE_URL"])
    flowforge.start_watchdog(timeout_seconds=300, interval_seconds=60)

    # Anywhere in your codebase
    from flowforge import Flow, Context

    flow = Flow("process_order")
    flow.step("charge",  charge_fn,  retries=3)
    flow.step("notify",  notify_fn,  retries=2)
    flow.run(Context({"amount": 100}), tracking_id="order_123")
"""

from flowforge.config import configure, reset, start_watchdog, stop_watchdog
from flowforge.context import Context
from flowforge.exceptions import (
    FlowAlreadyCompleted,
    FlowForgeNotConfigured,
    StepFailed,
    StepTimeoutError,
)
from flowforge.flow import Flow

__all__ = [
    # Configuration
    "configure",
    "reset",
    # Watchdog
    "start_watchdog",
    "stop_watchdog",
    # Core API
    "Flow",
    "Context",
    # Exceptions
    "FlowForgeNotConfigured",
    "StepFailed",
    "StepTimeoutError",
    "FlowAlreadyCompleted",
]

__version__ = "0.3.1"
