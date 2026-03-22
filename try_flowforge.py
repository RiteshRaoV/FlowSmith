"""
FlowForge — local smoke test
Run from the repo root:  python try_flowforge.py
No database needed — uses InMemoryStorage.
"""

from flowforge import Flow, Context
from flowforge.storage import InMemoryStorage


# ---------------------------------------------------------------------------
# Step functions — plain Python, exactly how a dev would write them
# ---------------------------------------------------------------------------

def get_product(ctx):
    product_id = ctx.data["product_id"]
    print(f"  [get_product] fetching product {product_id}...")

    # Simulated API response
    return {
        "name":     "Pro Subscription",
        "price":    4999,
        "currency": "USD",
    }


def get_payment_methods(ctx):
    product = ctx.data["get_product"]
    print(f"  [get_payment_methods] fetching methods for {product['currency']} {product['price']}...")

    # Simulated API response
    return {
        "methods": [
            {"id": "pm_card_visa",   "label": "Visa ending 4242"},
            {"id": "pm_card_master", "label": "Mastercard ending 1234"},
        ]
    }


def create_payment(ctx):
    product = ctx.data["get_product"]
    methods = ctx.data["get_payment_methods"]

    method   = methods["methods"][0]
    print(f"  [create_payment] charging {product['price']} via {method['label']}...")

    # Simulated API response
    return {
        "payment_id": "pay_abc123",
        "status":     "success",
    }


def send_notification(ctx):
    product = ctx.data["get_product"]
    payment = ctx.data["create_payment"]
    user_id = ctx.data["user_id"]

    print(f"  [send_notification] notifying user {user_id}...")
    print(f"    → order for '{product['name']}' | payment {payment['payment_id']}")

    return {"sent": True}


# ---------------------------------------------------------------------------
# Helper to build the flow
# ---------------------------------------------------------------------------

def build_flow(storage):
    flow = Flow("create_order", storage=storage)
    flow.step("get_product",         get_product,         retries=3)
    flow.step("get_payment_methods", get_payment_methods, retries=3)
    flow.step("create_payment",      create_payment,      retries=3)
    flow.step("send_notification",   send_notification,   retries=2)
    return flow


# ---------------------------------------------------------------------------
# Scenario 1: happy path
# ---------------------------------------------------------------------------

def test_happy_path():
    print("\n--- Scenario 1: happy path ---")

    storage = InMemoryStorage()
    flow    = build_flow(storage)
    ctx     = Context({"product_id": "prod_123", "user_id": "u_456"})

    flow.run(ctx, tracking_id="order_001")

    record = storage.get_flow("order_001")
    print(f"\n  Flow status : {record.status}")
    print(f"  Final ctx   : {ctx.data.keys()}")
    assert record.status == "COMPLETED"
    print("  PASS")


# ---------------------------------------------------------------------------
# Scenario 2: resume after a crash mid-flow
# ---------------------------------------------------------------------------

def test_resume():
    print("\n--- Scenario 2: resume after crash on step 3 ---")

    storage    = InMemoryStorage()
    call_log   = []

    def get_product_tracked(ctx):
        call_log.append("get_product")
        return get_product(ctx)

    def get_payment_methods_tracked(ctx):
        call_log.append("get_payment_methods")
        return get_payment_methods(ctx)

    def create_payment_flaky(ctx):
        call_log.append("create_payment")
        if call_log.count("create_payment") == 1:
            raise RuntimeError("payment gateway timeout")
        return create_payment(ctx)

    def send_notification_tracked(ctx):
        call_log.append("send_notification")
        return send_notification(ctx)

    # First run — crashes on create_payment
    flow1 = Flow("create_order", storage=storage)
    flow1.step("get_product",         get_product_tracked,         retries=1)
    flow1.step("get_payment_methods", get_payment_methods_tracked, retries=1)
    flow1.step("create_payment",      create_payment_flaky,        retries=1)
    flow1.step("send_notification",   send_notification_tracked,   retries=1)

    try:
        flow1.run(Context({"product_id": "prod_123", "user_id": "u_456"}), tracking_id="order_002")
    except Exception as e:
        print(f"\n  First run failed (expected): {e}")

    print(f"  Steps called so far: {call_log}")
    assert storage.get_flow("order_002").status == "FAILED"

    # Second run — same tracking_id, resumes from create_payment
    print("\n  Resuming with same tracking_id...")
    flow2 = Flow("create_order", storage=storage)
    flow2.step("get_product",         get_product_tracked,         retries=1)
    flow2.step("get_payment_methods", get_payment_methods_tracked, retries=1)
    flow2.step("create_payment",      create_payment_flaky,        retries=1)
    flow2.step("send_notification",   send_notification_tracked,   retries=1)

    flow2.run(Context({"product_id": "prod_123", "user_id": "u_456"}), tracking_id="order_002")

    print(f"\n  All steps called: {call_log}")
    print(f"  get_product called     : {call_log.count('get_product')}x  (expected 1 — skipped on resume)")
    print(f"  get_payment_methods    : {call_log.count('get_payment_methods')}x  (expected 1 — skipped on resume)")
    print(f"  create_payment called  : {call_log.count('create_payment')}x  (expected 2 — failed then retried)")
    print(f"  send_notification      : {call_log.count('send_notification')}x  (expected 1)")

    assert call_log.count("get_product")         == 1
    assert call_log.count("get_payment_methods") == 1
    assert call_log.count("create_payment")      == 2
    assert call_log.count("send_notification")   == 1
    assert storage.get_flow("order_002").status  == "COMPLETED"
    print("  PASS")


# ---------------------------------------------------------------------------
# Scenario 3: retry succeeds on second attempt
# ---------------------------------------------------------------------------

def test_retry():
    print("\n--- Scenario 3: step retries and succeeds ---")

    storage  = InMemoryStorage()
    attempts = {"n": 0}

    def flaky_product(ctx):
        attempts["n"] += 1
        print(f"  [get_product] attempt {attempts['n']}...")
        if attempts["n"] < 3:
            raise ConnectionError("API timeout")
        return {"name": "Basic Plan", "price": 999, "currency": "USD"}

    flow = Flow("create_order", storage=storage)
    flow.step("get_product", flaky_product, retries=3)

    flow.run(Context({"product_id": "prod_999", "user_id": "u_1"}), tracking_id="order_003")

    node = storage.get_node("order_003", "get_product")
    print(f"\n  Attempts made : {node.attempt_count}")
    print(f"  Node status   : {node.status}")
    assert node.attempt_count == 3
    assert node.status == "COMPLETED"
    print("  PASS")


# ---------------------------------------------------------------------------
# Scenario 4: inspect node-level execution trace
# ---------------------------------------------------------------------------

def test_inspect_trace():
    print("\n--- Scenario 4: inspect execution trace ---")

    storage = InMemoryStorage()
    flow    = build_flow(storage)
    ctx     = Context({"product_id": "prod_123", "user_id": "u_456"})

    flow.run(ctx, tracking_id="order_004")

    print("\n  Node-level trace:")
    for step_name in ["get_product", "get_payment_methods", "create_payment", "send_notification"]:
        node = storage.get_node("order_004", step_name)
        print(f"    {step_name:<26} status={node.status}  attempts={node.attempt_count}")
        print(f"      output: {node.output_data}")

    print("  PASS")


# ---------------------------------------------------------------------------
# Run all scenarios
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 55)
    print("  FlowForge smoke test")
    print("=" * 55)

    test_happy_path()
    test_resume()
    test_retry()
    test_inspect_trace()

    print("\n" + "=" * 55)
    print("  All scenarios passed.")
    print("=" * 55)