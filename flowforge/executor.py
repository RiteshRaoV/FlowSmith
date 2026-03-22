from flowforge.context import Context
from flowforge.exceptions import StepFailed
from flowforge.models import FlowRecord
from flowforge.step import Step
from flowforge.storage.base import StorageBackend


class Executor:
    """
    Runs the steps of a flow in order, handling:
      - Skip: if a node is already COMPLETED, restore its output and move on
      - Retry: attempt a step up to step.retries times before raising StepFailed
      - Persistence: write node status to storage before and after each attempt
    """

    def __init__(self, storage: StorageBackend):
        self._storage = storage

    def run(self, flow: FlowRecord, steps: list[Step], ctx: Context) -> None:
        """
        Execute all steps in order against the given flow record.
        Modifies ctx in-place as steps complete.
        """
        for step in steps:
            self._execute_step(flow, step, ctx)

    def _execute_step(self, flow: FlowRecord, step: Step, ctx: Context) -> None:
        node = self._storage.get_node(flow.id, step.name)

        # Already completed on a previous run — restore output and skip
        if node and node.status == "COMPLETED":
            if node.output_data:
                ctx.store(step.name, node.output_data)
            return

        # Attempt up to step.retries times
        last_exception = None
        for attempt in range(1, step.retries + 1):
            self._storage.start_node(
                flow_id=flow.id,
                step_name=step.name,
                input_data=ctx.snapshot(),
            )
            try:
                result = step.fn(ctx)
                output = result if isinstance(result, dict) else {}

                self._storage.complete_node(
                    flow_id=flow.id,
                    step_name=step.name,
                    output_data=output,
                )
                ctx.store(step.name, output)
                return  # success — move to next step

            except Exception as exc:
                last_exception = exc
                self._storage.fail_node(
                    flow_id=flow.id,
                    step_name=step.name,
                    error=str(exc),
                    attempt=attempt,
                )
                # If more attempts remain, loop — otherwise fall through

        raise StepFailed(
            step_name=step.name,
            attempt=step.retries,
            original=last_exception,
        )
