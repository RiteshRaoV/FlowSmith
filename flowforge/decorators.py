import contextvars
import functools
from collections.abc import Callable

from flowforge.flow import Flow

_current_flow = contextvars.ContextVar("_current_flow", default=None)


def step(
    name: str | Callable | None = None,
    *,
    retries: int = 1,
    backoff: str = "fixed",
    backoff_base: float = 0.0,
    timeout: int | None = None,
    condition: Callable | None = None,
):
    """
    Decorator to register a function as a step within a workflow builder.

    Can be used as:
        @step
        def my_step(ctx): ...

        @step(retries=3, backoff="exponential")
        def my_step(ctx): ...
    """
    def decorator(fn: Callable) -> Callable:
        step_name = name if isinstance(name, str) else fn.__name__
        flow = _current_flow.get()
        
        # If we are inside a @workflow builder context, register the step
        if flow is not None:
            flow.step(
                name=step_name,
                fn=fn,
                retries=retries,
                backoff=backoff,
                backoff_base=backoff_base,
                timeout=timeout,
                condition=condition,
            )
        return fn

    if callable(name):
        # Used as @step without parentheses
        return decorator(name)

    return decorator


def workflow(name: str | Callable | None = None):
    """
    Decorator to mark a function as a nested workflow builder.

    When the decorated function is called with (ctx, tracking_id), 
    it evaluates the inner function definitions to build the flow
    and then immediately executes the flow.
    """
    def decorator(fn: Callable) -> Callable:
        workflow_name = name if isinstance(name, str) else fn.__name__
        
        @functools.wraps(fn)
        def wrapper(ctx, tracking_id: str):
            flow = Flow(workflow_name)
            token = _current_flow.set(flow)
            
            try:
                # Calling the builder function evaluates the inner 
                # def blocks, triggering @step decorators to register steps
                fn()
            finally:
                _current_flow.reset(token)
            
            # Now that all steps are registered, execute the flow!
            flow.run(ctx, tracking_id=tracking_id)
            
        return wrapper

    if callable(name):
        # Used as @workflow without parentheses
        return decorator(name)

    return decorator
