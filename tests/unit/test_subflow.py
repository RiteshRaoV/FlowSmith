from flowforge.context import Context
from flowforge.decorators import step, subflow, workflow
from flowforge.flow import Flow
from flowforge.storage.memory import InMemoryStorage


def test_subflow_decorator():
    """Verify that @subflow natively executes another decorated workflow."""
    from flowforge import config
    config._storage = InMemoryStorage()

    logs = []

    # 1. Define the child workflow
    @workflow("child_flow")
    def my_child_flow():
        @step
        def child_init(ctx):
            logs.append(f"child_init:{ctx.data['uid']}")
            return {"child_done": True}

    # 2. Define the parent workflow
    @workflow("parent_flow")
    def my_parent_flow():
        @step
        def parent_init(ctx):
            logs.append("parent_init")

        @subflow
        def trigger_child(ctx):
            logs.append(f"trigger_child:{ctx.data['uid']}")
            # Return the child flow builder function and tracking ID
            return {
                "flow": my_child_flow,
                "tracking_id": f"child_{ctx.data['uid']}"
            }
        
    my_parent_flow(Context({"uid": "user_123"}), tracking_id="parent_t1")

    assert logs == [
        "parent_init",
        "trigger_child:user_123",
        "child_init:user_123"
    ]

def test_subflow_builder_api():
    """Verify native subflow handling in classic builder API."""
    from flowforge import config
    config._storage = InMemoryStorage()

    child = Flow("child_api")
    def child_fn(ctx):
        return {"done": True}
    child.step("c1", child_fn)

    parent = Flow("parent_api")
    
    # Use native subflow method
    parent.subflow(
        "trigger", 
        child, 
        tracking_id=lambda ctx: f"child_t_{ctx.data['id']}"
    )

    ctx = Context({"id": "abc"})
    parent.run(ctx, tracking_id="parent_t1")

    assert ctx.data["trigger"]["tracking_id"] == "child_t_abc"
    assert ctx.data["trigger"]["status"] == "COMPLETED"
    
    # Check that the child flow was actually stored in DB and completed
    child_record = config._storage.get_flow("child_t_abc")
    assert child_record.status == "COMPLETED"

