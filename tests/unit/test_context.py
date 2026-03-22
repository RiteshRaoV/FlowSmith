from flowforge.context import Context


def test_initial_data_is_accessible():
    ctx = Context({"amount": 100, "user_id": "u_1"})
    assert ctx.data["amount"] == 100
    assert ctx.data["user_id"] == "u_1"


def test_store_adds_step_output():
    ctx = Context({})
    ctx.store("charge_payment", {"payment_id": "pay_99"})
    assert ctx.data["charge_payment"]["payment_id"] == "pay_99"


def test_store_is_isolated_from_original():
    """Mutating stored output later should not affect ctx.data."""
    ctx = Context({})
    output = {"payment_id": "pay_99"}
    ctx.store("charge", output)
    output["payment_id"] = "MUTATED"
    assert ctx.data["charge"]["payment_id"] == "pay_99"


def test_snapshot_returns_copy():
    ctx = Context({"a": 1})
    snap = ctx.snapshot()
    snap["a"] = 999
    assert ctx.data["a"] == 1  # original unaffected


def test_empty_context():
    ctx = Context()
    assert ctx.data == {}
