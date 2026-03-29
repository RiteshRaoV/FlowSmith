"""
Unit tests for retry backoff strategies and per-step timeout.
No database needed — uses InMemoryStorage.
"""
import time

import pytest

from flowforge.context import Context
from flowforge.exceptions import StepFailed, StepTimeoutError
from flowforge.executor import Executor, _calc_backoff
from flowforge.step import Step
from flowforge.storage import InMemoryStorage


def make_executor():
    storage = InMemoryStorage()
    return Executor(storage), storage


def make_flow(storage, name="test"):
    return storage.create_flow(name, name, {})


# ---------------------------------------------------------------------------
# _calc_backoff
# ---------------------------------------------------------------------------

def test_fixed_backoff_is_constant():
    step = Step("s", lambda ctx: {}, retries=3, backoff="fixed", backoff_base=2.0)
    assert _calc_backoff(step, 1) == 2.0
    assert _calc_backoff(step, 2) == 2.0
    assert _calc_backoff(step, 3) == 2.0


def test_zero_backoff_base_returns_zero():
    step = Step("s", lambda ctx: {}, retries=3, backoff="exponential", backoff_base=0.0)
    assert _calc_backoff(step, 1) == 0.0


def test_exponential_backoff_doubles():
    step = Step("s", lambda ctx: {}, retries=5, backoff="exponential", backoff_base=1.0)
    assert _calc_backoff(step, 1) == 1.0   # 1 * 2^0
    assert _calc_backoff(step, 2) == 2.0   # 1 * 2^1
    assert _calc_backoff(step, 3) == 4.0   # 1 * 2^2


def test_exponential_backoff_capped_at_60s():
    step = Step("s", lambda ctx: {}, retries=10, backoff="exponential", backoff_base=1.0)
    # 1 * 2^10 = 1024 — should be capped
    assert _calc_backoff(step, 10) == 60.0


def test_jitter_backoff_is_within_range():
    step = Step("s", lambda ctx: {}, retries=3, backoff="jitter", backoff_base=1.0)
    # jitter = exp_delay + random(0, exp_delay)
    # for attempt=1: exp=1.0, so result should be in [1.0, 2.0]
    for _ in range(20):   # run multiple times to catch randomness issues
        delay = _calc_backoff(step, 1)
        assert 1.0 <= delay <= 2.0


def test_jitter_varies_between_calls():
    step = Step("s", lambda ctx: {}, retries=3, backoff="jitter", backoff_base=2.0)
    delays = {_calc_backoff(step, 1) for _ in range(20)}
    # With 20 samples, virtually impossible to get the exact same float twice
    assert len(delays) > 1


# ---------------------------------------------------------------------------
# Step validation
# ---------------------------------------------------------------------------

def test_invalid_backoff_strategy_raises():
    with pytest.raises(ValueError, match="backoff must be one of"):
        Step("s", lambda ctx: {}, backoff="random_thing")


def test_negative_backoff_base_raises():
    with pytest.raises(ValueError, match="backoff_base must be >= 0"):
        Step("s", lambda ctx: {}, backoff_base=-1.0)


def test_timeout_less_than_1_raises():
    with pytest.raises(ValueError, match="timeout must be >= 1"):
        Step("s", lambda ctx: {}, timeout=0)


# ---------------------------------------------------------------------------
# Backoff actually applied between retries
# ---------------------------------------------------------------------------

def test_backoff_delay_applied_between_retries():
    executor, storage = make_executor()
    flow = make_flow(storage)
    ctx = Context({})
    attempts = {"n": 0}
    timestamps = []

    def flaky(ctx):
        attempts["n"] += 1
        timestamps.append(time.monotonic())
        if attempts["n"] < 3:
            raise ValueError("fail")
        return {"ok": True}

    step = Step("flaky", flaky, retries=3, backoff="fixed", backoff_base=0.1)
    executor.run(flow, [step], ctx)

    assert attempts["n"] == 3
    # Gap between attempt 1→2 and 2→3 should each be >= 0.1s
    assert timestamps[1] - timestamps[0] >= 0.09
    assert timestamps[2] - timestamps[1] >= 0.09


def test_no_backoff_on_last_attempt():
    """Backoff should NOT be applied after the final failed attempt."""
    executor, storage = make_executor()
    flow = make_flow(storage)
    ctx = Context({})
    timestamps = []

    def always_fails(ctx):
        timestamps.append(time.monotonic())
        raise ValueError("boom")

    step = Step("bad", always_fails, retries=2, backoff="fixed", backoff_base=0.2)

    with pytest.raises(StepFailed):
        executor.run(flow, [step], ctx)

    assert len(timestamps) == 2
    # Gap between attempt 1 and 2 should have backoff
    assert timestamps[1] - timestamps[0] >= 0.15
    # No third timestamp — backoff not applied after last attempt


# ---------------------------------------------------------------------------
# Per-step timeout
# ---------------------------------------------------------------------------

def test_step_completes_within_timeout():
    executor, storage = make_executor()
    flow = make_flow(storage)
    ctx = Context({})

    def fast(ctx):
        return {"done": True}

    step = Step("fast", fast, timeout=5)
    executor.run(flow, [step], ctx)
    assert ctx.data["fast"]["done"] is True


def test_step_raises_step_failed_on_timeout():
    """A step that hangs past its timeout should raise StepFailed."""
    executor, storage = make_executor()
    flow = make_flow(storage)
    ctx = Context({})

    def hangs(ctx):
        time.sleep(10)   # will be killed by timeout
        return {}

    step = Step("hangs", hangs, retries=1, timeout=1)

    with pytest.raises(StepFailed) as exc_info:
        executor.run(flow, [step], ctx)

    assert isinstance(exc_info.value.original, StepTimeoutError)


def test_timeout_step_is_retried():
    """A timed-out step should be retried if attempts remain."""
    executor, storage = make_executor()
    flow = make_flow(storage)
    ctx = Context({})
    attempts = {"n": 0}

    def slow_then_fast(ctx):
        attempts["n"] += 1
        if attempts["n"] == 1:
            time.sleep(5)   # first attempt times out
        return {"ok": True}

    step = Step("s", slow_then_fast, retries=2, timeout=1)
    executor.run(flow, [step], ctx)

    assert attempts["n"] == 2
    assert ctx.data["s"]["ok"] is True


def test_timeout_node_marked_failed_in_storage():
    executor, storage = make_executor()
    flow = make_flow(storage)
    ctx = Context({})

    def hangs(ctx):
        time.sleep(10)
        return {}

    step = Step("hangs", hangs, retries=1, timeout=1)

    with pytest.raises(StepFailed):
        executor.run(flow, [step], ctx)

    node = storage.get_node(flow.id, "hangs")
    assert node.status == "FAILED"
    assert "timed out" in node.error.lower() or "timeout" in node.error.lower()
