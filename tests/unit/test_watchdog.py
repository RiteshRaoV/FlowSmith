"""
Unit tests for the Watchdog using InMemoryStorage.
No database or threading needed for most tests — we call _scan() directly.
"""
import time
from datetime import datetime, timezone, timedelta

import pytest

from flowforge.storage import InMemoryStorage
from flowforge.watchdog import Watchdog


def make_storage():
    return InMemoryStorage()


def make_watchdog(storage, timeout=10, interval=60):
    return Watchdog(storage=storage, timeout_seconds=timeout, interval_seconds=interval)


def backdate_node(storage, flow_id, step_name, seconds_ago):
    """Force a node's started_at into the past to simulate a crash."""
    key = f"{flow_id}:{step_name}"
    node = storage._nodes[key]
    node.started_at = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)


# ---------------------------------------------------------------------------
# get_stuck_nodes
# ---------------------------------------------------------------------------

def test_no_stuck_nodes_when_fresh():
    storage = make_storage()
    flow = storage.create_flow("f1", "test", {})
    storage.start_node("f1", "step_a", {})
    # Node just started — not stuck yet
    stuck = storage.get_stuck_nodes(timeout_seconds=300)
    assert stuck == []


def test_detects_stuck_node():
    storage = make_storage()
    storage.create_flow("f1", "test", {})
    storage.start_node("f1", "step_a", {})
    backdate_node(storage, "f1", "step_a", seconds_ago=400)

    stuck = storage.get_stuck_nodes(timeout_seconds=300)
    assert len(stuck) == 1
    assert stuck[0].step_name == "step_a"


def test_completed_node_not_detected():
    storage = make_storage()
    storage.create_flow("f1", "test", {})
    storage.start_node("f1", "step_a", {})
    storage.complete_node("f1", "step_a", {})
    backdate_node(storage, "f1", "step_a", seconds_ago=400)

    stuck = storage.get_stuck_nodes(timeout_seconds=300)
    assert stuck == []


def test_failed_node_not_detected():
    storage = make_storage()
    storage.create_flow("f1", "test", {})
    storage.start_node("f1", "step_a", {})
    storage.fail_node("f1", "step_a", "error", 1)
    backdate_node(storage, "f1", "step_a", seconds_ago=400)

    stuck = storage.get_stuck_nodes(timeout_seconds=300)
    assert stuck == []


# ---------------------------------------------------------------------------
# Watchdog._scan()
# ---------------------------------------------------------------------------

def test_scan_marks_stuck_node_failed():
    storage = make_storage()
    storage.create_flow("f1", "test", {})
    storage.start_node("f1", "step_a", {})
    backdate_node(storage, "f1", "step_a", seconds_ago=400)

    watchdog = make_watchdog(storage, timeout=300)
    watchdog._scan()

    node = storage.get_node("f1", "step_a")
    assert node.status == "FAILED"
    assert "Watchdog" in node.error


def test_scan_marks_parent_flow_failed():
    storage = make_storage()
    storage.create_flow("f1", "test", {})
    storage.start_node("f1", "step_a", {})
    backdate_node(storage, "f1", "step_a", seconds_ago=400)

    watchdog = make_watchdog(storage, timeout=300)
    watchdog._scan()

    flow = storage.get_flow("f1")
    assert flow.status == "FAILED"
    assert "Watchdog" in flow.error


def test_scan_does_nothing_when_no_stuck_nodes():
    storage = make_storage()
    storage.create_flow("f1", "test", {})
    storage.start_node("f1", "step_a", {})
    # Not backdated — not stuck

    watchdog = make_watchdog(storage, timeout=300)
    watchdog._scan()

    node = storage.get_node("f1", "step_a")
    assert node.status == "RUNNING"   # untouched


def test_scan_does_not_fail_already_failed_flow():
    """If the flow was already marked FAILED, watchdog should not double-fail."""
    storage = make_storage()
    storage.create_flow("f1", "test", {})
    storage.fail_flow("f1", "earlier error")
    storage.start_node("f1", "step_a", {})
    backdate_node(storage, "f1", "step_a", seconds_ago=400)

    watchdog = make_watchdog(storage, timeout=300)
    watchdog._scan()   # should not raise

    flow = storage.get_flow("f1")
    assert flow.status == "FAILED"
    assert flow.error == "earlier error"   # original error preserved


# ---------------------------------------------------------------------------
# Watchdog thread lifecycle
# ---------------------------------------------------------------------------

def test_watchdog_starts_and_stops():
    storage = make_storage()
    watchdog = Watchdog(storage=storage, timeout_seconds=300, interval_seconds=1)
    watchdog.start()
    assert watchdog.is_running
    watchdog.stop()
    assert not watchdog.is_running


def test_watchdog_detects_stuck_node_via_thread():
    """Full end-to-end — watchdog thread finds and fails a stuck node."""
    storage = make_storage()
    storage.create_flow("f1", "test", {})
    storage.start_node("f1", "step_a", {})
    backdate_node(storage, "f1", "step_a", seconds_ago=999)

    watchdog = Watchdog(storage=storage, timeout_seconds=300, interval_seconds=1)
    watchdog.start()
    time.sleep(2)   # let the thread run at least one scan
    watchdog.stop()

    node = storage.get_node("f1", "step_a")
    assert node.status == "FAILED"
    assert "Watchdog" in node.error


def test_start_watchdog_is_idempotent():
    """Calling start() twice should not spin up two threads."""
    storage = make_storage()
    watchdog = Watchdog(storage=storage, timeout_seconds=300, interval_seconds=60)
    watchdog.start()
    watchdog.start()   # second call — no-op
    assert watchdog.is_running
    watchdog.stop()


# ---------------------------------------------------------------------------
# Config-level API
# ---------------------------------------------------------------------------

def test_start_watchdog_raises_if_not_configured():
    import flowforge
    flowforge.reset()
    from flowforge.exceptions import FlowForgeNotConfigured
    with pytest.raises(FlowForgeNotConfigured):
        flowforge.start_watchdog()


def test_start_watchdog_via_config():
    import flowforge
    flowforge.reset()
    flowforge.configure(database_url="postgresql://u:p@localhost/db")

    # configure() doesn't connect — so get_storage() works but Watchdog
    # won't actually query DB. We just verify the thread starts.
    try:
        flowforge.start_watchdog(timeout_seconds=300, interval_seconds=60)
        from flowforge.config import _watchdog
        assert _watchdog is not None
        assert _watchdog.is_running
    finally:
        flowforge.stop_watchdog()
        flowforge.reset()
