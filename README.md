# FlowForge

Lightweight durable workflow execution for Python backends.

FlowForge fills the gap between fragile custom scripts and heavyweight orchestration systems like Temporal or Airflow. Define backend workflows as code, execute them reliably, and resume them safely after crashes — with zero external infrastructure beyond your existing database.

---

## The problem

Modern backend systems require orchestrating multiple API calls in sequence:

```python
product  = call_products_api(product_id)
methods  = call_payments_api(product["price"])
payment  = create_payment(methods[0]["id"])
notify(user_id, payment["id"])
```

Writing this is easy. Making it production-safe is not. What happens when:
- `create_payment` succeeds but the process crashes before `notify` runs?
- `call_payments_api` times out on attempt 1 but would succeed on attempt 2?
- You need to know exactly which step failed and why?

Without FlowForge you write custom retry logic, track state manually, and hope nothing crashes mid-flow. With FlowForge, every step is persisted, every failure is recoverable, and every execution is observable.

---

## Install

```bash
# PostgreSQL
pip install flowforge[postgres]

# MySQL
pip install flowforge[mysql]

# Both
pip install flowforge[postgres,mysql]
```

---

## Quickstart

**1. Configure once at server startup**

```python
import flowforge

flowforge.configure(database_url=os.environ["DATABASE_URL"])

# Optional but recommended — detects crashed nodes automatically
flowforge.start_watchdog(timeout_seconds=300, interval_seconds=60)
```

Supports both PostgreSQL and MySQL — FlowForge detects the right backend from the URL:

```bash
DATABASE_URL=postgresql://user:password@host:5432/mydb
DATABASE_URL=mysql://user:password@host:3306/mydb
```

**2. Run migrations**

```bash
flowforge migrate
# or explicitly
flowforge migrate --url postgresql://user:pass@localhost/mydb
```

This creates two tables in your database: `ff_flows` and `ff_nodes`.

**3. Define step functions**

Steps are plain Python functions. No base classes, no decorators, no magic.

```python
def get_product(ctx):
    product = products_api.get(ctx.data["product_id"])
    return {
        "name":     product["name"],
        "price":    product["price"],
        "currency": product["currency"],
    }

def get_payment_methods(ctx):
    product = ctx.data["get_product"]          # output from step 1
    methods = payments_api.list(
        price=product["price"],
        currency=product["currency"],
    )
    return {"methods": methods}

def create_payment(ctx):
    product = ctx.data["get_product"]          # output from step 1
    methods = ctx.data["get_payment_methods"]  # output from step 2
    payment = payments_api.create(
        method_id=methods["methods"][0]["id"],
        amount=product["price"],
    )
    return {"payment_id": payment["id"]}

def send_notification(ctx):
    product  = ctx.data["get_product"]         # output from step 1
    payment  = ctx.data["create_payment"]      # output from step 3
    user_id  = ctx.data["user_id"]             # original input
    email_api.send_receipt(user_id, payment["payment_id"], product["name"])
    return {"sent": True}
```

Each step receives a `Context` object (`ctx`). The output of every completed step is available on `ctx.data` under the step's name. This is how data flows between steps — no argument passing, no globals.

**4. Wire up the flow and run it**

```python
from flowforge import Flow, Context

flow = Flow("create_order")
flow.step("get_product",         get_product,         retries=3)
flow.step("get_payment_methods", get_payment_methods, retries=3)
flow.step("create_payment",      create_payment,      retries=3)
flow.step("send_notification",   send_notification,   retries=2)

flow.run(
    Context({"product_id": "prod_123", "user_id": "u_456"}),
    tracking_id=request.idempotency_key,
)
```

---

## Core guarantees

| Guarantee | What it means |
|-----------|---------------|
| Completed steps never re-run | If `get_product` succeeded, it is skipped on every subsequent retry |
| Resume from last success | A flow that failed on step 3 resumes at step 3, not step 1 |
| At-least-once execution | If a process crashes mid-step, that step will re-run on resume |
| Full execution trace | Every step's input, output, error, and attempt count is stored |
| Idempotent trigger | Calling `flow.run()` with the same `tracking_id` resumes, never duplicates |

> **Note on at-least-once:** FlowForge guarantees completed steps are never re-run. Steps that were *in progress* when a crash happened will be retried. Make your step functions idempotent (safe to run more than once) for full crash safety.

---

## The watchdog

The watchdog solves a subtle but critical problem: what happens when a process crashes *after* a node is marked `RUNNING` but *before* it is marked `COMPLETED`?

Without intervention, that node stays `RUNNING` in the database forever — the flow can never be resumed because FlowForge sees it as still in progress.

The watchdog is a background thread that periodically scans for nodes that have been `RUNNING` longer than your configured timeout. When it finds one, it marks the node `FAILED` and the parent flow `FAILED`, so the next `flow.run()` call can resume correctly.

```
10:00:02  Node starts      → status = RUNNING
10:00:02  Server crashes   → node frozen in RUNNING
          ...5 minutes...
10:05:00  Watchdog wakes   → finds node RUNNING for > 5 min
10:05:00  Watchdog marks   → node = FAILED, flow = FAILED
10:05:30  Server restarts  → flow.run(tracking_id="same-id")
10:05:30  FlowForge sees   → step 1 COMPLETED (skip)
10:05:30  FlowForge sees   → step 2 FAILED (retry from here) ✓
```

**Start it at server startup:**

```python
flowforge.configure(database_url=os.environ["DATABASE_URL"])
flowforge.start_watchdog(
    timeout_seconds=300,   # how long before a RUNNING node is considered stuck
    interval_seconds=60,   # how often to scan
)
```

Set `timeout_seconds` to at least 2x your slowest step's expected runtime. If your payment API can legitimately take 2 minutes, use a timeout of at least 5 minutes.

The watchdog runs as a daemon thread — it stops automatically when your process exits. No cleanup required.

---

## Resume behaviour

FlowForge uses `tracking_id` to identify a flow execution. Pass the same `tracking_id` to resume:

```python
# First run — crashes on step 3
flow.run(ctx, tracking_id="order_abc123")

# Resume — step 1 and 2 skipped automatically, resumes at step 3
flow.run(ctx, tracking_id="order_abc123")
```

| Flow status on second call | Behaviour |
|---------------------------|-----------|
| Not found | Fresh execution |
| `RUNNING` or `FAILED` | Resume from last completed step |
| `COMPLETED` | Raises `FlowAlreadyCompleted` |

---

## Database backends

FlowForge supports PostgreSQL and MySQL via the same `StorageBackend` interface. The backend is selected automatically from your database URL.

| URL prefix | Backend |
|------------|---------|
| `postgresql://` or `postgres://` | `PostgresStorage` |
| `mysql://` | `MySQLStorage` |

For testing, use `InMemoryStorage` — no database required:

```python
from flowforge.storage import InMemoryStorage

flow = Flow("test_flow", storage=InMemoryStorage())
flow.step("my_step", my_fn)
flow.run(ctx, tracking_id="test-1")
```

---

## Local development

```bash
# Start both databases
docker-compose up -d

# Run migrations
make migrate-postgres
make migrate-mysql

# Install dev dependencies
make install

# Unit tests — no database needed, runs in milliseconds
make test-unit

# Integration tests — requires running databases
make test-integration

# All tests with coverage
make test
```

---

## Project structure

```
flowforge/
├── flowforge/
│   ├── __init__.py        # public API: configure(), start_watchdog(), Flow, Context
│   ├── config.py          # global configure(), start_watchdog(), get_storage()
│   ├── flow.py            # Flow class — step registration and run()
│   ├── executor.py        # step execution loop, retry, resume logic
│   ├── watchdog.py        # background thread for stuck-node detection
│   ├── context.py         # Context — shared state between steps
│   ├── step.py            # Step dataclass
│   ├── exceptions.py      # FlowForgeNotConfigured, StepFailed, FlowAlreadyCompleted
│   ├── storage/
│   │   ├── base.py        # StorageBackend ABC — implement this to add a new backend
│   │   ├── postgres.py    # PostgreSQL backend
│   │   ├── mysql.py       # MySQL backend
│   │   └── memory.py      # In-memory backend for tests
│   ├── models/
│   │   ├── flow_record.py # FlowRecord dataclass
│   │   └── node_record.py # NodeRecord dataclass
│   ├── migrations/
│   │   ├── postgres/      # PostgreSQL migration files
│   │   └── mysql/         # MySQL migration files
│   └── contrib/           # Optional integrations — v0.2+ (decorator API, Django hook)
└── tests/
    ├── unit/              # Fast tests using InMemoryStorage — no infrastructure needed
    └── integration/       # Real database tests — requires docker-compose
```

---

## Roadmap

| Version | Scope |
|---------|-------|
| **v0.1.0** | Core engine, InMemoryStorage, sequential execution |
| **v0.2.0** | PostgresStorage, MySQLStorage, migrate CLI, watchdog ← current |
| v0.3.0 | Connection pooling, retry backoff strategies, per-step timeout |
| v0.4.0 | Parallel step execution, conditional branching |
| v0.5.0 | Async execution, DAG support |
| v1.0.0 | Stable API, battle tested in production |

---

## License

MIT
