
from flowsmith.context import Context
from flowsmith.decorators import step, workflow
from flowsmith.storage.memory import InMemoryStorage


def test_decorator_builder_and_conditional_branching():
    # Setup test
    storage = InMemoryStorage()
    
    # Needs to be injected globally for decorators
    import flowsmith.config
    flowsmith.config._storage = storage

    @workflow("my_branching_workflow")
    def process_test():
        
        @step(retries=1)
        def initial_step(ctx):
            return {"status": "ok", "value": 42}

        # This should execute because condition is True
        @step(condition=lambda ctx: ctx.data["initial_step"]["status"] == "ok")
        def step_true(ctx):
            return {"executed": True}

        # This should NOT execute because condition is False
        @step(condition=lambda ctx: ctx.data["initial_step"]["value"] > 100)
        def step_false(ctx):
            return {"executed": False}
            
        # This will fail and retry if called
        attempts = [0]
        @step(retries=2)
        def step_retry(ctx):
            attempts[0] += 1
            if attempts[0] < 2:
                raise ValueError("Fail once")
            return {"retried": True}

    ctx = Context()
    
    # Execute the flow
    process_test(ctx, tracking_id="test_run_123")
    
    # Assertions
    flow_record = storage.get_flow("test_run_123")
    assert flow_record is not None
    assert flow_record.status == "COMPLETED"
    
    # Check Context data populates correctly
    assert ctx.data["initial_step"]["status"] == "ok"
    assert ctx.data["step_true"]["executed"] is True
    
    # Ensure skipped step left no trace in ctx
    assert "step_false" not in ctx.data
    
    # Ensure retried step succeeded eventually
    assert ctx.data["step_retry"]["retried"] is True
    
    # Validate node records exactly match
    true_node = storage.get_node("test_run_123", "step_true")
    assert true_node is not None
    assert true_node.status == "COMPLETED"
    
    false_node = storage.get_node("test_run_123", "step_false")
    assert false_node is None  # Never inserted!
    
    # Cleanup global storage
    flowsmith.config.reset()
