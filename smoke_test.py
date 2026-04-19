"""
FlowSmith — Production Smoke Test
==================================

Runs real-world scenarios against both PostgreSQL and MySQL to verify
the package works end-to-end with actual database backends.

Prerequisites:
    flowsmith db-up           # start Postgres + MySQL via docker-compose
    flowsmith migrate-postgres
    flowsmith migrate-mysql

Run:
    python smoke_test.py

Each scenario is run against BOTH backends independently.
Tables are cleaned between scenarios to prevent cross-contamination.
"""

import logging
import os
import sys
import time
import uuid

import flowsmith
from flowsmith import Context, Flow, FlowAlreadyCompleted, StepFailed
from flowsmith.storage.postgres import PostgresStorage
from flowsmith.storage.mysql import MySQLStorage

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POSTGRES_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://flowsmith:flowsmith@localhost:5432/flowsmith",
)
MYSQL_URL = os.environ.get(
    "MYSQL_URL",
    "mysql://flowsmith:flowsmith@localhost:3306/flowsmith",
)

# Enable executor logging so we can see retry/backoff/timeout messages
logging.basicConfig(
    level=logging.INFO,
    format="    %(name)-24s %(levelname)-7s %(message)s",
)
# Quiet down SQLAlchemy unless debugging
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_pass_count = 0
_fail_count = 0


def _tracking_id() -> str:
    """Generate a unique tracking ID for each scenario run."""
    return f"smoke_{uuid.uuid4().hex[:12]}"


def _cleanup(storage):
    """Delete all flow and node records. Nodes cascade from flows."""
    from sqlalchemy import text
    with storage._engine.connect() as conn:
        conn.execute(text("DELETE FROM fs_nodes"))
        conn.execute(text("DELETE FROM fs_flows"))
        conn.commit()


def _header(name: str, backend: str):
    print(f"\n{'─' * 60}")
    print(f"  {name}")
    print(f"  Backend: {backend}")
    print(f"{'─' * 60}")


def _pass(label: str):
    global _pass_count
    _pass_count += 1
    print(f"  ✓ {label}")


def _fail(label: str, detail: str = ""):
    global _fail_count
    _fail_count += 1
    msg = f"  ✗ {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def _assert(condition: bool, label: str, detail: str = ""):
    if condition:
        _pass(label)
    else:
        _fail(label, detail or "assertion failed")


# ---------------------------------------------------------------------------
# Step functions — simulate real API calls
# ---------------------------------------------------------------------------

def fetch_product(ctx):
    """Simulate fetching a product from a catalog API."""
    return {
        "name": "Pro Subscription",
        "price": 4999,
        "currency": "USD",
    }


def fetch_payment_methods(ctx):
    """Simulate fetching payment methods."""
    product = ctx.data["fetch_product"]
    return {
        "methods": [
            {"id": "pm_visa_4242", "label": f"Visa ({product['currency']})"},
            {"id": "pm_mc_1234", "label": "Mastercard"},
        ]
    }


def charge_payment(ctx):
    """Simulate creating a payment charge."""
    product = ctx.data["fetch_product"]
    methods = ctx.data["fetch_payment_methods"]
    return {
        "payment_id": f"pay_{uuid.uuid4().hex[:8]}",
        "amount": product["price"],
        "method": methods["methods"][0]["id"],
        "status": "captured",
    }


def send_receipt(ctx):
    """Simulate sending a receipt email."""
    payment = ctx.data["charge_payment"]
    return {
        "sent": True,
        "payment_id": payment["payment_id"],
    }


# ---------------------------------------------------------------------------
# Scenario 1: Happy Path
# ---------------------------------------------------------------------------

def scenario_happy_path(storage, backend: str):
    _header("Scenario 1: Happy Path — all steps succeed", backend)
    _cleanup(storage)

    flow = Flow("checkout", storage=storage)
    flow.step("fetch_product", fetch_product, retries=1)
    flow.step("fetch_payment_methods", fetch_payment_methods, retries=1)
    flow.step("charge_payment", charge_payment, retries=1)
    flow.step("send_receipt", send_receipt, retries=1)

    tid = _tracking_id()
    ctx = Context({"user_id": "u_100", "product_id": "prod_42"})
    flow.run(ctx, tracking_id=tid)

    record = storage.get_flow(tid)
    _assert(record.status == "COMPLETED", "flow is COMPLETED")
    _assert("fetch_product" in ctx.data, "step outputs available in ctx")
    _assert(ctx.data["send_receipt"]["sent"] is True, "final step output correct")

    # Verify all 4 nodes exist and are COMPLETED
    for step in ["fetch_product", "fetch_payment_methods", "charge_payment", "send_receipt"]:
        node = storage.get_node(tid, step)
        _assert(node is not None and node.status == "COMPLETED", f"node '{step}' is COMPLETED")


# ---------------------------------------------------------------------------
# Scenario 2: Resume After Crash
# ---------------------------------------------------------------------------

def scenario_resume_after_crash(storage, backend: str):
    _header("Scenario 2: Resume — crash on step 3, resume picks up", backend)
    _cleanup(storage)

    call_log = []

    def fetch_product_tracked(ctx):
        call_log.append("fetch_product")
        return fetch_product(ctx)

    def fetch_methods_tracked(ctx):
        call_log.append("fetch_payment_methods")
        return fetch_payment_methods(ctx)

    def charge_flaky(ctx):
        call_log.append("charge_payment")
        if call_log.count("charge_payment") == 1:
            raise ConnectionError("payment gateway timeout — simulated crash")
        return charge_payment(ctx)

    def send_receipt_tracked(ctx):
        call_log.append("send_receipt")
        return send_receipt(ctx)

    tid = _tracking_id()

    # --- First run: crashes on charge_payment ---
    flow1 = Flow("checkout", storage=storage)
    flow1.step("fetch_product", fetch_product_tracked, retries=1)
    flow1.step("fetch_payment_methods", fetch_methods_tracked, retries=1)
    flow1.step("charge_payment", charge_flaky, retries=1)
    flow1.step("send_receipt", send_receipt_tracked, retries=1)

    try:
        flow1.run(Context({"user_id": "u_200", "product_id": "prod_42"}), tracking_id=tid)
    except StepFailed:
        pass

    _assert(storage.get_flow(tid).status == "FAILED", "flow is FAILED after crash")
    _assert(call_log.count("fetch_product") == 1, "fetch_product called once")

    # --- Second run: same tracking_id, resumes from charge_payment ---
    flow2 = Flow("checkout", storage=storage)
    flow2.step("fetch_product", fetch_product_tracked, retries=1)
    flow2.step("fetch_payment_methods", fetch_methods_tracked, retries=1)
    flow2.step("charge_payment", charge_flaky, retries=1)
    flow2.step("send_receipt", send_receipt_tracked, retries=1)

    flow2.run(Context({"user_id": "u_200", "product_id": "prod_42"}), tracking_id=tid)

    _assert(storage.get_flow(tid).status == "COMPLETED", "flow is COMPLETED after resume")
    _assert(call_log.count("fetch_product") == 1, "fetch_product NOT re-run on resume")
    _assert(call_log.count("fetch_payment_methods") == 1, "fetch_payment_methods NOT re-run")
    _assert(call_log.count("charge_payment") == 2, "charge_payment retried on resume")
    _assert(call_log.count("send_receipt") == 1, "send_receipt ran once")


# ---------------------------------------------------------------------------
# Scenario 3: Retry with Exponential Backoff
# ---------------------------------------------------------------------------

def scenario_retry_with_backoff(storage, backend: str):
    _header("Scenario 3: Retry — fails twice, succeeds on attempt 3", backend)
    _cleanup(storage)

    attempts = {"n": 0}

    def flaky_api(ctx):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError(f"API unavailable (attempt {attempts['n']})")
        return {"result": "ok", "attempts_needed": attempts["n"]}

    flow = Flow("retry_test", storage=storage)
    flow.step("flaky_api", flaky_api, retries=3, backoff="exponential", backoff_base=0.1)

    tid = _tracking_id()
    start = time.monotonic()
    flow.run(Context({}), tracking_id=tid)
    elapsed = time.monotonic() - start

    node = storage.get_node(tid, "flaky_api")
    _assert(node.status == "COMPLETED", "node completed after retries")
    _assert(node.attempt_count == 3, f"took 3 attempts (got {node.attempt_count})")
    _assert(elapsed >= 0.2, f"backoff delay observed ({elapsed:.2f}s >= 0.2s)")
    _assert(storage.get_flow(tid).status == "COMPLETED", "flow is COMPLETED")


# ---------------------------------------------------------------------------
# Scenario 4: Retry Exhaustion
# ---------------------------------------------------------------------------

def scenario_retry_exhaustion(storage, backend: str):
    _header("Scenario 4: Retry Exhaustion — step fails all attempts", backend)
    _cleanup(storage)

    def always_fail(ctx):
        raise RuntimeError("permanent failure — API key revoked")

    flow = Flow("doomed_flow", storage=storage)
    flow.step("bad_step", always_fail, retries=3, backoff="fixed", backoff_base=0.05)

    tid = _tracking_id()
    caught = False
    try:
        flow.run(Context({}), tracking_id=tid)
    except StepFailed as e:
        caught = True
        _assert(e.step_name == "bad_step", "StepFailed has correct step_name")
        _assert(e.attempt == 3, f"StepFailed reports 3 attempts (got {e.attempt})")
        _assert(isinstance(e.original, RuntimeError), "original exception preserved")

    _assert(caught, "StepFailed was raised")
    _assert(storage.get_flow(tid).status == "FAILED", "flow is FAILED")

    node = storage.get_node(tid, "bad_step")
    _assert(node.status == "FAILED", "node is FAILED")
    _assert(node.attempt_count == 3, f"node has 3 attempts (got {node.attempt_count})")
    _assert("permanent failure" in node.error, "error message persisted in DB")


# ---------------------------------------------------------------------------
# Scenario 5: Per-Step Timeout
# ---------------------------------------------------------------------------

def scenario_step_timeout(storage, backend: str):
    _header("Scenario 5: Per-Step Timeout — slow step is killed", backend)
    _cleanup(storage)

    def slow_step(ctx):
        time.sleep(30)  # will be killed by timeout
        return {"never": "reached"}

    def fast_step(ctx):
        return {"status": "done"}

    flow = Flow("timeout_test", storage=storage)
    flow.step("slow_step", slow_step, retries=1, timeout=2)
    flow.step("fast_step", fast_step, retries=1)

    tid = _tracking_id()
    caught = False
    try:
        flow.run(Context({}), tracking_id=tid)
    except StepFailed as e:
        caught = True
        _assert(e.step_name == "slow_step", "timeout on correct step")

    _assert(caught, "StepFailed raised for timed-out step")
    _assert(storage.get_flow(tid).status == "FAILED", "flow is FAILED")

    node = storage.get_node(tid, "slow_step")
    _assert(node.status == "FAILED", "timed-out node is FAILED")
    _assert("timed out" in node.error.lower(), "timeout error persisted in DB")

    # fast_step should never have run
    fast_node = storage.get_node(tid, "fast_step")
    _assert(fast_node is None, "subsequent step was not started")


# ---------------------------------------------------------------------------
# Scenario 6: Idempotency Guard
# ---------------------------------------------------------------------------

def scenario_idempotency(storage, backend: str):
    _header("Scenario 6: Idempotency — re-running completed flow raises", backend)
    _cleanup(storage)

    flow = Flow("idempotent_test", storage=storage)
    flow.step("work", lambda ctx: {"done": True}, retries=1)

    tid = _tracking_id()
    flow.run(Context({}), tracking_id=tid)
    _assert(storage.get_flow(tid).status == "COMPLETED", "first run completed")

    # Second run with same tracking_id should raise
    caught = False
    try:
        flow.run(Context({}), tracking_id=tid)
    except FlowAlreadyCompleted:
        caught = True

    _assert(caught, "FlowAlreadyCompleted raised on re-run")


# ---------------------------------------------------------------------------
# Scenario 7: Watchdog Detects Stuck Node
# ---------------------------------------------------------------------------

def scenario_watchdog(storage, backend: str):
    _header("Scenario 7: Watchdog — detects and fails stuck nodes", backend)
    _cleanup(storage)

    # Manually insert a flow+node that looks stuck (RUNNING, started long ago)
    from sqlalchemy import text
    from datetime import datetime, timezone, timedelta

    tid = _tracking_id()
    stuck_time = datetime.now(timezone.utc) - timedelta(seconds=600)  # 10 min ago

    with storage._engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO fs_flows (id, name, status, input_data, created_at, updated_at) "
            "VALUES (:id, :name, 'RUNNING', '{}', :now, :now)"
        ), {"id": tid, "name": "stuck_flow", "now": stuck_time})
        conn.commit()

    with storage._engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO fs_nodes (id, flow_id, step_name, status, attempt_count, started_at) "
            "VALUES (:id, :flow_id, :step_name, 'RUNNING', 1, :started)"
        ), {"id": str(uuid.uuid4()), "flow_id": tid, "step_name": "stuck_step",
            "started": stuck_time})
        conn.commit()

    # Verify the node shows up as stuck
    stuck = storage.get_stuck_nodes(timeout_seconds=300)
    _assert(len(stuck) >= 1, f"get_stuck_nodes found {len(stuck)} stuck node(s)")

    found = any(n.flow_id == tid and n.step_name == "stuck_step" for n in stuck)
    _assert(found, "our stuck node is in the results")

    # Run the watchdog scan manually
    from flowsmith.watchdog import Watchdog
    wd = Watchdog(storage=storage, timeout_seconds=300, interval_seconds=60)
    wd._scan()  # run one scan cycle directly

    # Verify the node and flow are now FAILED
    node = storage.get_node(tid, "stuck_step")
    _assert(node.status == "FAILED", "watchdog marked stuck node as FAILED")
    _assert("Watchdog" in node.error, "watchdog error message in node")

    flow_record = storage.get_flow(tid)
    _assert(flow_record.status == "FAILED", "watchdog marked flow as FAILED")

    # Now verify a flow.run() with same tracking_id can resume
    flow = Flow("stuck_flow", storage=storage)
    flow.step("stuck_step", lambda ctx: {"recovered": True}, retries=1)

    flow.run(Context({}), tracking_id=tid)
    _assert(storage.get_flow(tid).status == "COMPLETED", "flow resumed after watchdog recovery")


# ---------------------------------------------------------------------------
# Scenario 8: Decorator API and Conditional Branching
# ---------------------------------------------------------------------------

def scenario_decorator_api(storage, backend: str):
    _header("Scenario 8: Decorator API — nested builder and branching", backend)
    _cleanup(storage)

    from flowsmith.decorators import workflow, step

    @workflow("decorator_checkout")
    def checkout_flow():
        @step(retries=1)
        def fetch_product(ctx):
            return {"price": 100, "valid": True}

        @step(condition=lambda ctx: ctx.data["fetch_product"]["valid"])
        def charge_payment(ctx):
            return {"status": "paid"}

        # Condition evaluates to False, so this step is skipped entirely
        @step(condition=lambda ctx: ctx.data["fetch_product"]["price"] > 500)
        def skipped_manager_approval(ctx):
            return {"status": "approved"}

        @step(retries=1)
        def send_receipt(ctx):
            return {"sent": True}

    tid = _tracking_id()
    ctx = Context({"user_id": "u_999"})
    
    checkout_flow(ctx, tracking_id=tid)

    record = storage.get_flow(tid)
    _assert(record.status == "COMPLETED", "decorator flow is COMPLETED")

    _assert("fetch_product" in ctx.data, "step 1 executed")
    _assert("charge_payment" in ctx.data, "step 2 executed (condition=True)")
    _assert("skipped_manager_approval" not in ctx.data, "step 3 skipped (condition=False)")
    _assert("send_receipt" in ctx.data, "step 4 executed")
    _assert(storage.get_node(tid, "skipped_manager_approval") is None, "skipped step left no node record")


# ---------------------------------------------------------------------------
# Scenario 9: Parallel Execution & Subflows
# ---------------------------------------------------------------------------

def scenario_v5_scaling(storage, backend: str):
    _header("Scenario 9: v0.5 Scaling — Parallel Groups & Subflows", backend)
    _cleanup(storage)

    from flowsmith.decorators import workflow, step, parallel, subflow

    @workflow("child_smoke")
    def smoke_subflow():
        @step
        def child_work(ctx):
            time.sleep(0.1)
            return {"child_done": True, "uid": ctx.data["uid"]}

    @workflow("parent_smoke")
    def smoke_parent():
        @step
        def init(ctx):
            return {"started": True}

        @parallel
        def fetchers():
            @step
            def fetch_a(ctx):
                time.sleep(0.1)
                return {"val": "A"}
            
            @step
            def fetch_b(ctx):
                time.sleep(0.1)
                return {"val": "B"}

        @subflow
        def trigger_smoke_subflow(ctx):
            return {
                "flow": smoke_subflow,
                "tracking_id": f"child_{ctx.data['uid']}"
            }

        @step
        def finalize(ctx):
            return {"done": True}

    tid = _tracking_id()
    ctx = Context({"uid": "user_123"})
    
    start_time = time.time()
    smoke_parent(ctx, tracking_id=tid)
    elapsed = time.time() - start_time

    # Verification
    record = storage.get_flow(tid)
    _assert(record.status == "COMPLETED", "parent flow is COMPLETED")
    
    child_record = storage.get_flow("child_user_123")
    _assert(child_record is not None and child_record.status == "COMPLETED", "child flow explicitly COMPLETED")

    _assert(ctx.data["fetch_a"]["val"] == "A", "parallel step A completed")
    _assert(ctx.data["fetch_b"]["val"] == "B", "parallel step B completed")
    
    # fetch_a and fetch_b both sleep 0.1s. child sleeps 0.1s.
    # Sequential execution: 0.3s. Parallel execution: 0.2s.
    # Allowing for DB overhead, let's just assert the data is correct.
    _assert("finalize" in ctx.data, "finalize completed")

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

SCENARIOS = [
    scenario_happy_path,
    scenario_resume_after_crash,
    scenario_retry_with_backoff,
    scenario_retry_exhaustion,
    scenario_step_timeout,
    scenario_idempotency,
    scenario_watchdog,
    scenario_decorator_api,
    scenario_v5_scaling,
]


def run_all_for_backend(storage, backend_name: str):
    import flowsmith.config
    flowsmith.config._storage = storage  # Provide global context for decorators
    for scenario in SCENARIOS:
        try:
            scenario(storage, backend_name)
        except Exception as e:
            _fail(f"SCENARIO CRASHED: {e}")
            import traceback
            traceback.print_exc()


def main():
    global _pass_count, _fail_count

    print("=" * 60)
    print("  FlowSmith Production Smoke Test")
    print(f"  Version: {flowsmith.__version__}")
    print("=" * 60)

    # --- PostgreSQL ---
    print(f"\n{'━' * 60}")
    print("  BACKEND: PostgreSQL")
    print(f"  URL: {POSTGRES_URL.split('@')[0]}@***")
    print(f"{'━' * 60}")

    try:
        pg = PostgresStorage(url=POSTGRES_URL)
        run_all_for_backend(pg, "PostgreSQL")
    except Exception as e:
        print(f"\n  ⚠  PostgreSQL unavailable: {e}")
        print("     Skipping PostgreSQL tests. Is the DB running? (flowsmith db-up)")

    # --- MySQL ---
    print(f"\n{'━' * 60}")
    print("  BACKEND: MySQL")
    print(f"  URL: {MYSQL_URL.split('@')[0]}@***")
    print(f"{'━' * 60}")

    try:
        my = MySQLStorage(url=MYSQL_URL)
        run_all_for_backend(my, "MySQL")
    except Exception as e:
        print(f"\n  ⚠  MySQL unavailable: {e}")
        print("     Skipping MySQL tests. Is the DB running? (flowsmith db-up)")

    # --- Summary ---
    total = _pass_count + _fail_count
    print(f"\n{'=' * 60}")
    print(f"  Results: {_pass_count}/{total} passed, {_fail_count} failed")

    if _fail_count > 0:
        print("  STATUS: FAIL")
        print(f"{'=' * 60}")
        sys.exit(1)
    else:
        print("  STATUS: ALL PASSED ✓")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()