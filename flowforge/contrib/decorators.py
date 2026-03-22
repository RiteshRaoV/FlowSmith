# flowforge/contrib/decorators.py
#
# Decorator API — planned for v0.2
# Not imported by default. Opt-in via:
#   from flowforge.contrib.decorators import workflow, step
#
# This file is a placeholder. Implementation will follow in v0.2.

raise NotImplementedError(
    "The FlowForge decorator API is planned for v0.2 and is not yet implemented. "
    "Use the Flow API instead:\n\n"
    "    flow = Flow('my_workflow')\n"
    "    flow.step('step_one', fn, retries=3)\n"
    "    flow.run(ctx, tracking_id='...')"
)
