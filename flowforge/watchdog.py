"""
FlowForge Watchdog

Detects nodes stuck in RUNNING status after a process crash and
transitions them to FAILED so the flow can be resumed.

Usage:
    import flowforge
    flowforge.configure(database_url=os.environ["DATABASE_URL"])
    flowforge.start_watchdog(timeout_seconds=300, interval_seconds=60)

The watchdog runs in a daemon thread — it stops automatically when
the main process exits. No cleanup required.
"""

import logging
import threading
from typing import Any

logger = logging.getLogger("flowforge.watchdog")


class Watchdog:
    """
    Background thread that periodically scans for stuck nodes.

    A node is considered stuck if:
      - status = RUNNING
      - started_at < now() - timeout_seconds

    On detection:
      1. Node  → FAILED  (error = "Watchdog: node exceeded timeout")
      2. Flow  → FAILED  (error = "Watchdog: flow has stuck nodes")

    The flow can then be resumed by calling flow.run() with the same tracking_id.
    """

    def __init__(
        self,
        storage: Any,
        timeout_seconds: int = 300,
        interval_seconds: int = 60,
    ) -> None:
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be >= 1")
        if interval_seconds < 1:
            raise ValueError("interval_seconds must be >= 1")

        self._storage = storage
        self._timeout_seconds = timeout_seconds
        self._interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the watchdog background thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("Watchdog is already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="flowforge-watchdog",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Watchdog started — timeout=%ss, interval=%ss",
            self._timeout_seconds,
            self._interval_seconds,
        )

    def stop(self) -> None:
        """Signal the watchdog to stop. Blocks until the thread exits."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._interval_seconds + 2)
        logger.info("Watchdog stopped.")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        """Main watchdog loop — runs until stop() is called."""
        while not self._stop_event.is_set():
            try:
                self._scan()
            except Exception as e:
                # Never crash the watchdog — log and keep going
                logger.error("Watchdog scan error: %s", e, exc_info=True)
            # Sleep in small increments so stop() is responsive
            self._stop_event.wait(timeout=self._interval_seconds)

    def _scan(self) -> None:
        """Find stuck nodes and mark them failed."""
        stuck = self._storage.get_stuck_nodes(timeout_seconds=self._timeout_seconds)
        if not stuck:
            return

        logger.warning("Watchdog found %d stuck node(s)", len(stuck))

        failed_flows = set()

        for node in stuck:
            logger.warning(
                "  Stuck node: flow_id=%s step=%s started_at=%s",
                node.flow_id, node.step_name, node.started_at,
            )
            self._storage.fail_node(
                flow_id=node.flow_id,
                step_name=node.step_name,
                error=(
                    f"Watchdog: node exceeded timeout of {self._timeout_seconds}s. "
                    "Process likely crashed. Resume the flow with the same tracking_id."
                ),
                attempt=node.attempt_count,
            )
            failed_flows.add(node.flow_id)

        for flow_id in failed_flows:
            # Only fail the flow if it's still RUNNING
            flow = self._storage.get_flow(flow_id)
            if flow and flow.status == "RUNNING":
                self._storage.fail_flow(
                    flow_id=flow_id,
                    error=(
                        "Watchdog: flow failed due to stuck node(s). "
                        "Resume with the same tracking_id."
                    ),
                )
                logger.warning("  Flow %s marked FAILED by watchdog", flow_id)
