import pytest

from flowsmith.context import Context
from flowsmith.exceptions import StepFailed
from flowsmith.executor import Executor
from flowsmith.step import Step
from flowsmith.storage import InMemoryStorage


def make_executor():
    storage = InMemoryStorage()
    return Executor(storage), storage


def make_flow_record(storage, tracking_id="flow-1", name="test_flow"):
    return storage.create_flow(tracking_id=tracking_id, name=name, input_data={})


def test_single_step_completes():
    executor, storage = make_executor()
    flow = make_flow_record(storage)
    ctx = Context({})

    executor.run(flow, [Step(name="say_hello", fn=lambda ctx: {"msg": "hello"})], ctx)

    assert ctx.data["say_hello"]["msg"] == "hello"
    assert storage.get_node(flow.id, "say_hello").status == "COMPLETED"


def test_output_is_available_to_next_step():
    executor, storage = make_executor()
    flow = make_flow_record(storage)
    ctx = Context({})

    def step_a(ctx):
        return {"value": 42}

    def step_b(ctx):
        return {"doubled": ctx.data["step_a"]["value"] * 2}

    executor.run(flow, [Step("step_a", step_a), Step("step_b", step_b)], ctx)
    assert ctx.data["step_b"]["doubled"] == 84


def test_multiple_steps_all_complete():
    executor, storage = make_executor()
    flow = make_flow_record(storage)
    ctx = Context({})
    calls = []

    steps = [
        Step(name, lambda ctx, n=name: calls.append(n) or {})
        for name in ["a", "b", "c"]
    ]
    executor.run(flow, steps, ctx)
    assert calls == ["a", "b", "c"]


def test_completed_step_is_skipped_on_resume():
    executor, storage = make_executor()
    flow = make_flow_record(storage)

    storage.start_node(flow.id, "step_a", {})
    storage.complete_node(flow.id, "step_a", {"result": "cached"})

    call_count = {"n": 0}

    def step_a(ctx):
        call_count["n"] += 1
        return {"result": "fresh"}

    ctx = Context({})
    executor.run(flow, [Step("step_a", step_a)], ctx)

    assert call_count["n"] == 0
    assert ctx.data["step_a"]["result"] == "cached"


def test_resume_skips_completed_runs_failed():
    """
    Simulates a crash after step_a completed but step_b failed.
    On resume: step_a skipped, step_b retried.
    """
    executor, storage = make_executor()
    flow = make_flow_record(storage)

    storage.start_node(flow.id, "step_a", {})
    storage.complete_node(flow.id, "step_a", {"val": 1})

    a_calls = {"n": 0}
    b_calls = {"n": 0}

    def step_a(ctx):
        a_calls["n"] += 1
        return {}

    def step_b(ctx):
        b_calls["n"] += 1
        return {"done": True}

    ctx = Context({})
    executor.run(flow, [Step("step_a", step_a), Step("step_b", step_b)], ctx)

    assert a_calls["n"] == 0
    assert b_calls["n"] == 1


def test_step_succeeds_on_second_attempt():
    executor, storage = make_executor()
    flow = make_flow_record(storage)
    ctx = Context({})
    attempts = {"n": 0}

    def flaky(ctx):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise ValueError("temporary failure")
        return {"ok": True}

    executor.run(flow, [Step("flaky", flaky, retries=3)], ctx)
    assert attempts["n"] == 2
    assert ctx.data["flaky"]["ok"] is True


def test_step_raises_step_failed_after_exhausting_retries():
    executor, storage = make_executor()
    flow = make_flow_record(storage)
    ctx = Context({})

    def always_fails(ctx):
        raise RuntimeError("boom")

    with pytest.raises(StepFailed) as exc_info:
        executor.run(flow, [Step("bad_step", always_fails, retries=3)], ctx)

    err = exc_info.value
    assert err.step_name == "bad_step"
    assert err.attempt == 3
    assert isinstance(err.original, RuntimeError)


def test_node_status_is_failed_after_exhausting_retries():
    executor, storage = make_executor()
    flow = make_flow_record(storage)
    ctx = Context({})

    def always_fails(ctx):
        raise RuntimeError("boom")

    with pytest.raises(StepFailed):
        executor.run(flow, [Step("bad_step", always_fails, retries=2)], ctx)

    node = storage.get_node(flow.id, "bad_step")
    assert node.status == "FAILED"
    assert "boom" in node.error
