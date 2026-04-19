import ctypes
import logging
import platform
import random
import threading
import time
from contextlib import suppress
from typing import Any

from flowsmith.context import Context
from flowsmith.exceptions import StepFailed, StepTimeoutError
from flowsmith.models import FlowRecord
from flowsmith.step import ParallelGroup, Step
from flowsmith.storage.base import StorageBackend

logger = logging.getLogger("flowsmith.executor")

# Grace period given to a timed-out thread to clean up after receiving
# StepTimeoutError before the hard kill fires.
_HARD_KILL_GRACE_SECONDS = 2

# Thread ident type varies by platform — unsigned on Windows, signed on
# Linux/macOS.  Using the wrong type causes ctypes to silently target the
# wrong thread (or no thread at all).
_THREAD_ID_TYPE = ctypes.c_ulong if platform.system() == "Windows" else ctypes.c_ulong


def _calc_backoff(step: Step, attempt: int) -> float:
    """
    Calculate the delay in seconds before the next retry attempt.

    attempt is 1-indexed — attempt=1 means the first failure just happened,
    so we're calculating the delay before attempt 2.

    Strategies:
        fixed       — constant backoff_base seconds every retry
        exponential — backoff_base * 2^(attempt-1), capped at 60s
        jitter      — exponential base + uniform random jitter up to the base
                       avoids thundering herd when many flows retry simultaneously
    """
    if step.backoff_base == 0.0:
        return 0.0

    if step.backoff == "fixed":
        return step.backoff_base

    # exponential base: backoff_base * 2^(attempt-1)
    exp_delay = step.backoff_base * (2 ** (attempt - 1))
    exp_delay = min(exp_delay, 60.0)   # cap at 60s

    if step.backoff == "exponential":
        return float(exp_delay)

    # jitter: exponential + random noise up to the exponential value
    # keeps retries spread out even when many processes crash simultaneously
    return float(exp_delay + random.uniform(0, exp_delay))


def _raise_in_thread(thread: threading.Thread, exc_type: type) -> None:
    """
    Inject an exception into a running thread using ctypes.

    This is the standard Python pattern for interrupting a thread from outside.
    The exception is delivered at the next Python bytecode boundary — it will
    NOT interrupt a thread blocked in a C extension or I/O syscall.
    If the thread is stuck in C code, the hard kill grace period fires instead.
    """
    if thread.ident is None:
        raise ValueError("Thread is not started")
        
    result = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        _THREAD_ID_TYPE(thread.ident),
        ctypes.py_object(exc_type),
    )
    if result == 0:
        raise ValueError(f"Thread {thread.ident} not found — already finished?")
    if result > 1:
        # More than one thread affected — undo and raise
        ctypes.pythonapi.PyThreadState_SetAsyncExc(_THREAD_ID_TYPE(thread.ident), None)
        raise SystemError("PyThreadState_SetAsyncExc affected multiple threads")


class _StepRunner:
    """
    Runs a single step function in a worker thread with optional timeout.

    Timeout behaviour (when step.timeout is set):
      1. Step runs in a daemon worker thread.
      2. Main thread waits up to step.timeout seconds.
      3. On timeout: inject StepTimeoutError into the worker thread (clean kill).
      4. Give the worker _HARD_KILL_GRACE_SECONDS to finish cleanup.
      5. If still running: hard kill via ctypes (brutal — last resort).

    Without timeout: step runs in the calling thread directly (no overhead).
    """

    def __init__(self, step: Step, ctx: Context):
        self._step = step
        self._ctx = ctx
        self._result = None
        self._exception: Exception | None = None
        self._thread: threading.Thread | None = None

    def run(self) -> dict[str, Any]:
        """
        Execute the step. Returns the step's output dict.
        Raises StepTimeoutError or any exception thrown by the step function.
        """
        if self._step.timeout is None:
            return self._run_direct()
        return self._run_with_timeout()

    def _run_direct(self) -> dict[str, Any]:
        """Run step in the calling thread — no timeout, no overhead."""
        result = self._step.fn(self._ctx)
        return result if isinstance(result, dict) else {}

    def _run_with_timeout(self) -> dict[str, Any]:
        """Run step in a worker thread, enforce timeout."""
        self._thread = threading.Thread(
            target=self._worker,
            daemon=True,
            name=f"ff-step-{self._step.name}",
        )
        self._thread.start()
        self._thread.join(timeout=self._step.timeout)

        if not self._thread.is_alive():
            # Step finished within timeout
            if self._exception is not None:
                raise self._exception
            return self._result if isinstance(self._result, dict) else {}

        # ---- Timeout exceeded ----

        # Step 1: clean kill — inject StepTimeoutError into the worker
        with suppress(ValueError, SystemError): # thread already finished between join() and here
            _raise_in_thread(self._thread, StepTimeoutError)

        # Step 2: give it grace period to handle the exception and clean up
        self._thread.join(timeout=_HARD_KILL_GRACE_SECONDS)

        if self._thread.is_alive():
            # Step 3: hard kill — thread is stuck in C code or ignoring exception
            # This is a last resort — the thread becomes a zombie but the
            # main process can continue. Log the situation clearly.
            with suppress(ValueError, SystemError):# thread already finished between join() and here
                _raise_in_thread(self._thread, SystemExit)

        raise StepTimeoutError(
            step_name=self._step.name,
            timeout=self._step.timeout or 0,
            attempt=1,   # caller will set the real attempt number
        )

    def _worker(self) -> None:
        """Worker thread body — captures result or exception."""
        try:
            self._result = self._step.fn(self._ctx)
        except Exception as exc:
            self._exception = exc


class Executor:
    """
    Runs the steps of a flow in order, handling:
      - Skip:    completed steps are never re-run, output is restored to ctx
      - Retry:   attempt a step up to step.retries times before raising StepFailed
      - Backoff: configurable delay between retries (fixed, exponential, jitter)
      - Timeout: steps exceeding step.timeout seconds are killed and retried
    """

    def __init__(self, storage: StorageBackend):
        self._storage = storage

    def run(self, flow: FlowRecord, steps: list[Step | ParallelGroup], ctx: Context) -> None:
        """
        Execute all steps (or step groups) in order. Modifies ctx in-place as tasks complete.
        """
        for item in steps:
            if isinstance(item, ParallelGroup):
                self._execute_group(flow, item, ctx)
            else:
                self._execute_step(flow, item, ctx)

    def _execute_group(self, flow: FlowRecord, group: ParallelGroup, ctx: Context) -> None:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if not group.steps:
            return

        with ThreadPoolExecutor(max_workers=len(group.steps)) as pool:
            futures = [
                pool.submit(self._execute_step, flow, step, ctx) 
                for step in group.steps
            ]

            exceptions = []
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    exceptions.append(exc)
            
            if exceptions:
                # Raise the first exception to fail the group iteration
                raise exceptions[0]

    def _execute_step(self, flow: FlowRecord, step: Step, ctx: Context) -> None:
        node = self._storage.get_node(flow.id, step.name)

        # Already completed on a previous run — restore output and skip
        if node and node.status == "COMPLETED":
            if node.output_data:
                ctx.store(step.name, node.output_data)
            logger.debug("Step '%s' already completed — skipped", step.name)
            return

        if step.condition is not None and not step.condition(ctx):
            logger.info("Step '%s' condition evaluated to False — skipped", step.name)
            return

        last_exception: Exception | None = None

        for attempt in range(1, step.retries + 1):
            logger.info(
                "Step '%s' starting (attempt %d/%d)",
                step.name, attempt, step.retries,
            )
            self._storage.start_node(
                flow_id=flow.id,
                step_name=step.name,
                input_data=ctx.snapshot(),
            )
            try:
                runner = _StepRunner(step, ctx)
                output = runner.run()

                self._storage.complete_node(
                    flow_id=flow.id,
                    step_name=step.name,
                    output_data=output,
                )
                ctx.store(step.name, output)
                logger.info("Step '%s' completed (attempt %d/%d)", step.name, attempt, step.retries)
                return   # success

            except StepTimeoutError as exc:
                # Re-raise with the correct attempt number
                exc.attempt = attempt
                last_exception = exc
                self._storage.fail_node(
                    flow_id=flow.id,
                    step_name=step.name,
                    error=str(exc),
                    attempt=attempt,
                )
                logger.warning(
                    "Step '%s' timed out after %ds (attempt %d/%d)",
                    step.name, step.timeout, attempt, step.retries,
                )

            except Exception as exc:
                last_exception = exc
                self._storage.fail_node(
                    flow_id=flow.id,
                    step_name=step.name,
                    error=str(exc),
                    attempt=attempt,
                )
                logger.warning(
                    "Step '%s' failed (attempt %d/%d): %s",
                    step.name, attempt, step.retries, exc,
                )

            # Apply backoff before next attempt (not after last failure)
            if attempt < step.retries:
                delay = _calc_backoff(step, attempt)
                if delay > 0:
                    logger.info(
                        "Step '%s' retrying in %.1fs (%s backoff)",
                        step.name, delay, step.backoff,
                    )
                    time.sleep(delay)

        raise StepFailed(
            step_name=step.name,
            attempt=step.retries,
            original=last_exception or Exception("Unknown error"),
        )

