"""
Integration tests for SQLiteStorage.

No external services required — uses a temporary database file.

Run:
    pytest tests/integration/test_sqlite_storage.py -v -m integration
"""
import time
import uuid

import pytest

from flowsmith.__main__ import run_migrations_sqlite
from flowsmith.storage.sqlite import SQLiteStorage

pytestmark = pytest.mark.integration


@pytest.fixture
def sqlite_storage(tmp_path):
    url = f"sqlite:///{(tmp_path / 'flowsmith.db').as_posix()}"
    run_migrations_sqlite(url)
    storage = SQLiteStorage(url=url)
    yield storage
    storage.close()


def test_create_and_get_flow(sqlite_storage):
    fid = f"test-{uuid.uuid4()}"
    flow = sqlite_storage.create_flow(fid, "test_flow", {"x": 1})
    assert flow.status == "RUNNING"

    fetched = sqlite_storage.get_flow(fid)
    assert fetched.id == fid
    assert fetched.input_data == {"x": 1}
    assert fetched.created_at.tzinfo is not None


def test_complete_flow(sqlite_storage):
    fid = f"test-{uuid.uuid4()}"
    sqlite_storage.create_flow(fid, "test_flow", {})
    sqlite_storage.complete_flow(fid, {"result": "done"})

    flow = sqlite_storage.get_flow(fid)
    assert flow.status == "COMPLETED"
    assert flow.output_data == {"result": "done"}


def test_fail_flow(sqlite_storage):
    fid = f"test-{uuid.uuid4()}"
    sqlite_storage.create_flow(fid, "test_flow", {})
    sqlite_storage.fail_flow(fid, "something broke")

    flow = sqlite_storage.get_flow(fid)
    assert flow.status == "FAILED"
    assert "something broke" in flow.error


def test_node_lifecycle(sqlite_storage):
    fid = f"test-{uuid.uuid4()}"
    sqlite_storage.create_flow(fid, "test_flow", {})

    node = sqlite_storage.start_node(fid, "step_one", {"input": 1})
    assert node.status == "RUNNING"
    assert node.attempt_count == 1

    sqlite_storage.complete_node(fid, "step_one", {"output": 2})
    node = sqlite_storage.get_node(fid, "step_one")
    assert node.status == "COMPLETED"
    assert node.output_data == {"output": 2}


def test_node_retry_increments_attempt(sqlite_storage):
    fid = f"test-{uuid.uuid4()}"
    sqlite_storage.create_flow(fid, "test_flow", {})

    sqlite_storage.start_node(fid, "flaky_step", {})
    sqlite_storage.fail_node(fid, "flaky_step", "timeout", 1)

    node = sqlite_storage.start_node(fid, "flaky_step", {})
    assert node.attempt_count == 2
    assert node.status == "RUNNING"
    assert node.error is None


def test_get_flow_returns_none_for_missing(sqlite_storage):
    assert sqlite_storage.get_flow("does-not-exist") is None


def test_get_node_returns_none_for_missing(sqlite_storage):
    fid = f"test-{uuid.uuid4()}"
    sqlite_storage.create_flow(fid, "test_flow", {})
    assert sqlite_storage.get_node(fid, "nonexistent_step") is None


def test_get_stuck_nodes(sqlite_storage):
    fid = f"test-{uuid.uuid4()}"
    sqlite_storage.create_flow(fid, "test_flow", {})
    sqlite_storage.start_node(fid, "slow_step", {})
    time.sleep(1.1)

    assert [n.step_name for n in sqlite_storage.get_stuck_nodes(1)] == ["slow_step"]
    assert sqlite_storage.get_stuck_nodes(3600) == []
