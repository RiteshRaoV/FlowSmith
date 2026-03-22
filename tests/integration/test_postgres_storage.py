"""
Integration tests for PostgresStorage.

Requirements:
    docker-compose up -d postgres
    make migrate-postgres

Run:
    pytest tests/integration/test_postgres_storage.py -v -m integration
"""
import os
import uuid
import pytest

pytestmark = pytest.mark.integration

PG_URL = "postgresql://flowforge:flowforge@localhost/flowforge"


@pytest.fixture(scope="module")
def pg_storage():
    url = os.environ.get("DATABASE_URL", PG_URL)
    try:
        from flowforge.storage.postgres import PostgresStorage
        storage = PostgresStorage(url=url)
        yield storage
        storage._conn.close()
    except Exception as e:
        pytest.skip(f"Postgres not available: {e}")


@pytest.fixture(autouse=True)
def cleanup(pg_storage):
    """Remove test rows after each test."""
    yield
    cur = pg_storage._conn.cursor()
    cur.execute("DELETE FROM ff_nodes WHERE flow_id LIKE 'test-%'")
    cur.execute("DELETE FROM ff_flows WHERE id LIKE 'test-%'")
    pg_storage._conn.commit()
    cur.close()


def test_create_and_get_flow(pg_storage):
    fid = f"test-{uuid.uuid4()}"
    flow = pg_storage.create_flow(fid, "test_flow", {"x": 1})
    assert flow.status == "RUNNING"

    fetched = pg_storage.get_flow(fid)
    assert fetched.id == fid
    assert fetched.input_data == {"x": 1}


def test_complete_flow(pg_storage):
    fid = f"test-{uuid.uuid4()}"
    pg_storage.create_flow(fid, "test_flow", {})
    pg_storage.complete_flow(fid, {"result": "done"})

    flow = pg_storage.get_flow(fid)
    assert flow.status == "COMPLETED"
    assert flow.output_data == {"result": "done"}


def test_fail_flow(pg_storage):
    fid = f"test-{uuid.uuid4()}"
    pg_storage.create_flow(fid, "test_flow", {})
    pg_storage.fail_flow(fid, "something broke")

    flow = pg_storage.get_flow(fid)
    assert flow.status == "FAILED"
    assert "something broke" in flow.error


def test_node_lifecycle(pg_storage):
    fid = f"test-{uuid.uuid4()}"
    pg_storage.create_flow(fid, "test_flow", {})

    node = pg_storage.start_node(fid, "step_one", {"input": 1})
    assert node.status == "RUNNING"
    assert node.attempt_count == 1

    pg_storage.complete_node(fid, "step_one", {"output": 2})
    node = pg_storage.get_node(fid, "step_one")
    assert node.status == "COMPLETED"
    assert node.output_data == {"output": 2}


def test_node_retry_increments_attempt(pg_storage):
    fid = f"test-{uuid.uuid4()}"
    pg_storage.create_flow(fid, "test_flow", {})

    pg_storage.start_node(fid, "flaky_step", {})
    pg_storage.fail_node(fid, "flaky_step", "timeout", 1)

    node = pg_storage.start_node(fid, "flaky_step", {})
    assert node.attempt_count == 2


def test_get_flow_returns_none_for_missing(pg_storage):
    result = pg_storage.get_flow("does-not-exist")
    assert result is None


def test_get_node_returns_none_for_missing(pg_storage):
    fid = f"test-{uuid.uuid4()}"
    pg_storage.create_flow(fid, "test_flow", {})
    result = pg_storage.get_node(fid, "nonexistent_step")
    assert result is None
