"""
Integration tests for MySQLStorage.

Requirements:
    docker-compose up -d mysql
    make migrate-mysql

Run:
    pytest tests/integration/test_mysql_storage.py -v -m integration
"""
import os
import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

MYSQL_URL = "mysql://flowforge:flowforge@localhost/flowforge"


@pytest.fixture(scope="module")
def mysql_storage():
    url = os.environ.get("MYSQL_URL", MYSQL_URL)
    try:
        from flowforge.storage.mysql import MySQLStorage
        storage = MySQLStorage(url=url)
        yield storage
        storage._engine.dispose()
    except Exception as e:
        pytest.skip(f"MySQL not available: {e}")


@pytest.fixture(autouse=True)
def cleanup(mysql_storage):
    """Remove test rows after each test."""
    yield
    with mysql_storage._conn() as conn:
        conn.execute(text("DELETE FROM ff_nodes WHERE flow_id LIKE 'test-%'"))
        conn.execute(text("DELETE FROM ff_flows WHERE id LIKE 'test-%'"))
        conn.commit()


def test_create_and_get_flow(mysql_storage):
    fid = f"test-{uuid.uuid4()}"
    flow = mysql_storage.create_flow(fid, "test_flow", {"x": 1})
    assert flow.status == "RUNNING"

    fetched = mysql_storage.get_flow(fid)
    assert fetched.id == fid
    assert fetched.input_data == {"x": 1}


def test_complete_flow(mysql_storage):
    fid = f"test-{uuid.uuid4()}"
    mysql_storage.create_flow(fid, "test_flow", {})
    mysql_storage.complete_flow(fid, {"result": "done"})

    flow = mysql_storage.get_flow(fid)
    assert flow.status == "COMPLETED"
    assert flow.output_data == {"result": "done"}


def test_fail_flow(mysql_storage):
    fid = f"test-{uuid.uuid4()}"
    mysql_storage.create_flow(fid, "test_flow", {})
    mysql_storage.fail_flow(fid, "something broke")

    flow = mysql_storage.get_flow(fid)
    assert flow.status == "FAILED"
    assert "something broke" in flow.error


def test_node_lifecycle(mysql_storage):
    fid = f"test-{uuid.uuid4()}"
    mysql_storage.create_flow(fid, "test_flow", {})

    node = mysql_storage.start_node(fid, "step_one", {"input": 1})
    assert node.status == "RUNNING"
    assert node.attempt_count == 1

    mysql_storage.complete_node(fid, "step_one", {"output": 2})
    node = mysql_storage.get_node(fid, "step_one")
    assert node.status == "COMPLETED"
    assert node.output_data == {"output": 2}


def test_node_retry_increments_attempt(mysql_storage):
    fid = f"test-{uuid.uuid4()}"
    mysql_storage.create_flow(fid, "test_flow", {})

    mysql_storage.start_node(fid, "flaky_step", {})
    mysql_storage.fail_node(fid, "flaky_step", "timeout", 1)

    node = mysql_storage.start_node(fid, "flaky_step", {})
    assert node.attempt_count == 2


def test_get_flow_returns_none_for_missing(mysql_storage):
    result = mysql_storage.get_flow("does-not-exist")
    assert result is None


def test_get_node_returns_none_for_missing(mysql_storage):
    fid = f"test-{uuid.uuid4()}"
    mysql_storage.create_flow(fid, "test_flow", {})
    result = mysql_storage.get_node(fid, "nonexistent_step")
    assert result is None
