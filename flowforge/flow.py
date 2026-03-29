import contextlib
from collections.abc import Callable

from flowforge.context import Context
from flowforge.exceptions import FlowAlreadyCompleted
from flowforge.executor import Executor
from flowforge.step import ParallelGroup, Step
from flowforge.storage.base import StorageBackend


class Flow:
    """
    Defines a named workflow as an ordered sequence of steps.

    Usage (production — uses global config):
        flow = Flow("process_order")
        flow.step("charge_payment",   charge_payment,   retries=3)
        flow.step("create_order",     create_order,     retries=3)
        flow.step("send_confirmation", send_confirmation, retries=2)
        flow.run(ctx, tracking_id="order_abc123")

    Usage (testing — local storage override):
        flow = Flow("process_order", storage=InMemoryStorage())
        ...
    """

    def __init__(self, name: str, storage: StorageBackend | None = None):
        self.name = name
        self._steps: list[Step | ParallelGroup] = []
        self._storage_override = storage
        self._active_parallel_group: ParallelGroup | None = None

    @contextlib.contextmanager
    def parallel(self):
        """
        Context manager to bundle subsequent step() calls into a ParallelGroup.
        When executed, all steps in this group run concurrently.
        """
        group = ParallelGroup(steps=[])
        self._active_parallel_group = group
        try:
            yield
        finally:
            self._active_parallel_group = None
            if group.steps:
                self._steps.append(group)

    def step(
        self,
        name: str,
        fn: Callable,
        retries: int = 1,
        backoff: str = "fixed",
        backoff_base: float = 0.0,
        timeout: int | None = None,
        condition: Callable | None = None,
    ) -> "Flow":
        """
        Register a step on this flow.

        Args:
            name:         Unique step identifier. Used as the DB key and ctx.data key.
            fn:           Callable with signature (ctx: Context) -> dict.
            retries:      Total attempts including the first. retries=3 means
                          the step will be tried up to 3 times before failing.
            backoff:      Delay strategy between retries.
                            "fixed"       — constant backoff_base seconds
                            "exponential" — backoff_base * 2^(attempt-1), capped at 60s
                            "jitter"      — exponential + random noise (avoids thundering herd)
            backoff_base: Base delay in seconds. Default 0.0 (instant retry).
            timeout:      Max seconds a single attempt may run. None = no timeout.
                          On timeout: StepTimeoutError is raised and the attempt
                          counts as a failure — retried if attempts remain.
            condition:    Predicate func (ctx: Context) -> bool. If returns False,
                          the step is skipped during execution.

        Returns self for optional chaining.
        """
        step_obj = Step(
            name=name,
            fn=fn,
            retries=retries,
            backoff=backoff,
            backoff_base=backoff_base,
            timeout=timeout,
            condition=condition,
        )
        if self._active_parallel_group is not None:
            self._active_parallel_group.steps.append(step_obj)
        else:
            self._steps.append(step_obj)
        return self

    def subflow(
        self,
        name: str,
        flow: "Flow",
        get_tracking_id: Callable[[Context], str],
        retries: int = 1,
        backoff: str = "fixed",
        backoff_base: float = 0.0,
        timeout: int | None = None,
        condition: Callable | None = None,
    ) -> "Flow":
        """
        Formally register an embedded sub-flow as a step execution.

        Args:
            flow:             The Flow instance to trigger.
            get_tracking_id:  Lambda mapping current Context to the child flow's tracking_id.
        """
        def _subflow_runner(ctx: Context) -> dict:
            tid = get_tracking_id(ctx)
            flow.run(ctx, tracking_id=tid)
            return {"tracking_id": tid, "status": "COMPLETED"}

        return self.step(
            name=name,
            fn=_subflow_runner,
            retries=retries,
            backoff=backoff,
            backoff_base=backoff_base,
            timeout=timeout,
            condition=condition,
        )

    def run(self, ctx: Context, tracking_id: str) -> None:
        """
        Execute the flow.

        If tracking_id already exists in the DB:
          - COMPLETED → raises FlowAlreadyCompleted
          - RUNNING / FAILED → resumes from last successful step

        If tracking_id does not exist → starts a fresh execution.

        Args:
            ctx:         Context carrying the initial input data.
            tracking_id: Caller-supplied idempotency key. Use a value that
                         is stable across retries, e.g. request.idempotency_key.
        """
        storage = self._get_storage()
        executor = Executor(storage)

        flow = storage.get_flow(tracking_id)

        if flow is None:
            flow = storage.create_flow(
                tracking_id=tracking_id,
                name=self.name,
                input_data=ctx.snapshot(),
            )
        elif flow.status == "COMPLETED":
            raise FlowAlreadyCompleted(tracking_id)
        # RUNNING or FAILED → resume (executor handles step-level skipping)

        try:
            executor.run(flow, self._steps, ctx)
            storage.complete_flow(
                flow_id=flow.id,
                output_data=ctx.snapshot(),
            )
        except Exception as exc:
            storage.fail_flow(flow_id=flow.id, error=str(exc))
            raise

    def _get_storage(self) -> StorageBackend:
        if self._storage_override is not None:
            return self._storage_override
        from flowforge.config import get_storage
        return get_storage()
