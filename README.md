# FlowForge

Lightweight durable workflow execution for Python backends.

FlowForge fills the gap between fragile custom scripts and heavyweight orchestration systems like Temporal or Airflow. Define backend workflows as code, execute them reliably, and resume them safely after crashes.

## Install

```bash
pip install flowforge[postgres]
```

## Quickstart

```python
# 1. Configure once at server startup
import flowforge
flowforge.configure(database_url=os.environ["DATABASE_URL"])

# 2. Define step functions — plain Python, no magic
def charge_payment(ctx):
    result = payment_client.charge(ctx.data["amount"])
    return {"payment_id": result.id}

def create_order(ctx):
    payment_id = ctx.data["charge_payment"]["payment_id"]
    return {"order_id": order_client.create(payment_id).id}

def send_confirmation(ctx):
    email_client.send(ctx.data["create_order"]["order_id"])
    return {"sent": True}

# 3. Wire up the flow and run it
from flowforge import Flow, Context

flow = Flow("process_order")
flow.step("charge_payment",    charge_payment,   retries=3)
flow.step("create_order",      create_order,     retries=3)
flow.step("send_confirmation", send_confirmation, retries=2)

flow.run(
    Context({"amount": 4999, "card_token": "tok_abc"}),
    tracking_id=request.idempotency_key,
)
```

## Core guarantees

- Completed steps are **never re-run** after success
- Workflow resumes from the **last successful step** after a crash
- Full per-step execution trace stored: input, output, error, attempt count
- At-least-once semantics — step functions should be idempotent

## Run migrations

```bash
export DATABASE_URL=postgresql://user:pass@localhost/mydb
make migrate
```

## Development

```bash
# Start local Postgres
make db-up

# Install dev dependencies
make install

# Run unit tests (no Postgres needed)
make test-unit

# Run all tests including integration
make test
```

## Project structure

```
flowforge/
├── flowforge/
│   ├── __init__.py       # public API: configure(), Flow, Context
│   ├── config.py         # global configure() / get_storage()
│   ├── flow.py           # Flow class
│   ├── executor.py       # step execution, retry, resume logic
│   ├── context.py        # Context class
│   ├── step.py           # Step dataclass
│   ├── exceptions.py     # typed exceptions
│   ├── storage/
│   │   ├── base.py       # StorageBackend ABC
│   │   ├── postgres.py   # production backend
│   │   └── memory.py     # test backend
│   ├── models/
│   │   ├── flow_record.py
│   │   └── node_record.py
│   ├── migrations/       # raw SQL, framework-agnostic
│   └── contrib/          # optional integrations (v0.2+)
└── tests/
    ├── unit/             # fast, no infrastructure
    └── integration/      # requires Postgres via docker-compose
```

## License

MIT
