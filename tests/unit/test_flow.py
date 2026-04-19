import pytest

from flowsmith import Context, Flow
from flowsmith.exceptions import FlowAlreadyCompleted, FlowSmithNotConfigured, StepFailed
from flowsmith.storage import InMemoryStorage


def make_flow(name="test_flow"):
    return Flow(name, storage=InMemoryStorage())


def test_flow_raises_if_not_configured_and_no_override():
    """
    Flow with no storage override should raise FlowSmithNotConfigured
    when run() is called without configure() having been called first.
    """
    flow = Flow("unconfigured_flow")
    flow.step("noop", lambda ctx: {})
    with pytest.raises(FlowSmithNotConfigured):
        flow.run(Context({}), tracking_id="t1")


def test_run_completes_successfully():
    flow = make_flow()
    flow.step("greet", lambda ctx: {"msg": "hi"})
    flow.run(Context({}), tracking_id="run-1")

    record = flow._get_storage().get_flow("run-1")
    assert record.status == "COMPLETED"


def test_flow_stores_final_output():
    storage = InMemoryStorage()
    flow = Flow("my_flow", storage=storage)
    flow.step("produce", lambda ctx: {"answer": 42})
    flow.run(Context({}), tracking_id="run-1")

    record = storage.get_flow("run-1")
    assert record.output_data["produce"]["answer"] == 42


def test_step_chaining_returns_self():
    storage = InMemoryStorage()
    flow = Flow("chain", storage=storage)
    result = flow.step("a", lambda ctx: {}).step("b", lambda ctx: {})
    assert result is flow


def test_resume_continues_from_failed_flow():
    storage = InMemoryStorage()
    call_log = []

    def step_a(ctx):
        call_log.append("a")
        return {"val": 1}

    def step_b(ctx):
        call_log.append("b")
        if call_log.count("b") < 2:
            raise RuntimeError("transient")
        return {"val": 2}

    flow = Flow("resume_test", storage=storage)
    flow.step("step_a", step_a, retries=1)
    flow.step("step_b", step_b, retries=1)

    with pytest.raises(StepFailed):
        flow.run(Context({}), tracking_id="r1")

    assert call_log == ["a", "b"]

    flow2 = Flow("resume_test", storage=storage)
    flow2.step("step_a", step_a, retries=1)
    flow2.step("step_b", step_b, retries=1)
    flow2.run(Context({}), tracking_id="r1")

    assert call_log == ["a", "b", "b"]
    assert storage.get_flow("r1").status == "COMPLETED"


def test_run_raises_if_flow_already_completed():
    storage = InMemoryStorage()
    flow = Flow("done_flow", storage=storage)
    flow.step("noop", lambda ctx: {})
    flow.run(Context({}), tracking_id="done-1")

    with pytest.raises(FlowAlreadyCompleted):
        flow.run(Context({}), tracking_id="done-1")


def test_failed_step_marks_flow_as_failed():
    storage = InMemoryStorage()
    flow = Flow("fail_flow", storage=storage)
    flow.step("bad", lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")), retries=1)

    with pytest.raises(StepFailed):
        flow.run(Context({}), tracking_id="f1")

    record = storage.get_flow("f1")
    assert record.status == "FAILED"
    assert "boom" in record.error


def test_flow_condition_parameter():
    """
    Test that the condition argument on Flow.step bypasses execution.
    """
    storage = InMemoryStorage()
    flow = Flow("condition_flow", storage=storage)
    
    # Step 1 always runs
    flow.step("step_1", lambda ctx: {"run": True})
    
    # Step 2 condition evaluates to True -> will execute
    flow.step(
        "step_2", 
        lambda ctx: {"executed": True},
        condition=lambda ctx: ctx.data["step_1"]["run"] is True
    )
    
    # Step 3 condition evaluates to False -> will skip
    flow.step(
        "step_3", 
        lambda ctx: {"executed": False}, 
        condition=lambda ctx: ctx.data.get("step_2", {}).get("missing_key") == "yes"
    )
    
    ctx = Context({})
    flow.run(ctx, tracking_id="cond-1")
    
    # Verify outputs populated correctly
    assert ctx.data["step_1"]["run"] is True
    assert ctx.data["step_2"]["executed"] is True
    assert "step_3" not in ctx.data  # Skipped, output not stored
    
    # Verify skipped step created no DB record
    assert storage.get_node("cond-1", "step_3") is None

