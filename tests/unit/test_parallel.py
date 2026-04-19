import time

from flowsmith.context import Context
from flowsmith.decorators import parallel, step, workflow
from flowsmith.flow import Flow
from flowsmith.storage.memory import InMemoryStorage


def test_parallel_decorator():
    """Verify that parallel blocks execute concurrently."""
    storage = InMemoryStorage()

    logs = []

    @workflow("data_pipeline")
    def process():
        @step
        def init(ctx):
            logs.append("init")
        
        @parallel
        def fetchers():
            @step
            def fetch_a(ctx):
                time.sleep(0.1)
                logs.append("A")
                return {"val": "A"}

            @step
            def fetch_b(ctx):
                logs.append("B")
                return {"val": "B"}

            @step
            def fetch_c(ctx):
                time.sleep(0.05)
                logs.append("C")
                return {"val": "C"}

        @step
        def finalize(ctx):
            logs.append("finalize")
            return {
                "a": ctx.data["fetch_a"]["val"],
                "b": ctx.data["fetch_b"]["val"],
                "c": ctx.data["fetch_c"]["val"],
            }

    # Execute
    ctx = Context()
    
    from flowsmith import config
    config._storage = storage

    process(ctx, tracking_id="t1")

    # Due to concurrent execution:
    # B sleeps 0s, C sleeps 0.05s, A sleeps 0.1s
    # So order should be: init, B, C, A, finalize
    assert set(logs) == {"init", "A", "B", "C", "finalize"}
    # Because they launch virtually instantly, logs could occasionally vary in exact insertion race conditions, 
    # but the delay is large enough to assert order generally. Let's assert exactly.
    assert logs == ["init", "B", "C", "A", "finalize"]
    
    assert ctx.data["finalize"] == {"a": "A", "b": "B", "c": "C"}
    config._storage = None

def test_parallel_builder_api():
    """Verify Classic Builder API for parallel steps."""
    storage = InMemoryStorage()
    flow = Flow("builder_pipeline", storage=storage)
    
    logs = []
    
    def fetch_1(ctx):
        time.sleep(0.1)
        logs.append("1")
    def fetch_2(ctx):
        logs.append("2")
        
    def final(ctx):
        logs.append("final")

    with flow.parallel():
        flow.step("fetch_1", fetch_1)
        flow.step("fetch_2", fetch_2)
    
    flow.step("final", final)

    flow.run(Context(), tracking_id="b1")
    assert logs == ["2", "1", "final"]
