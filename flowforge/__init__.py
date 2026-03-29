"""
FlowForge — lightweight durable workflow execution for Python backends.

Quickstart:
    import flowforge

    # 1. Configure once at server startup
    flowforge.configure(database_url=os.environ["DATABASE_URL"])
    flowforge.start_watchdog(timeout_seconds=300, interval_seconds=60)

    # -------------------------------------------------------------------------
    # Flavor 1: The Classic Builder API
    # -------------------------------------------------------------------------
    # Ideal for explicit control and dynamically generating workflows.
    from flowforge import Flow, Context

    flow = Flow("process_order")
    flow.step("charge",  charge_fn,  retries=3)
    flow.step("notify",  notify_fn,  retries=2)
    
    # Execute manually
    flow.run(Context({"amount": 100}), tracking_id="order_123")

    # -------------------------------------------------------------------------
    # Flavor 2: The Decorator API (v0.4+)
    # -------------------------------------------------------------------------
    # Ideal for readable, declarative workflows with built-in branching.
    from flowforge import Context
    from flowforge.decorators import workflow, step

    @workflow("process_order")
    def order_flow():
        
        @step(retries=3)
        def charge_user(ctx):
            return {"paid": True}

        # Branching handles skipping inherently!
        @step(condition=lambda ctx: ctx.data["charge_user"]["paid"])
        def notify_user(ctx):
            pass

    # Trigger execution (resumes automatically if crashed before)
    order_flow(Context({"amount": 100}), tracking_id="order_123")
"""

from flowforge.config import configure, reset, start_watchdog, stop_watchdog
from flowforge.context import Context
from flowforge.decorators import step, workflow
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
    # Decorators
    "workflow",
    "step",
    # Exceptions
    "FlowForgeNotConfigured",
    "StepFailed",
    "StepTimeoutError",
    "FlowAlreadyCompleted",
]

__version__ = "0.4.0"
