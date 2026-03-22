"""
Integration tests for crash recovery and resume using real PostgreSQL.

Requirements:
    - Docker running: make db-up
    - Migrations applied: make migrate
    - DATABASE_URL set: export DATABASE_URL=postgresql://flowforge:flowforge@localhost/flowforge

Run with:
    make test-integration
    # or
    pytest tests/integration/ -v -m integration
"""
import os

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def db_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping integration tests")
    return url


def test_placeholder(db_url):
    """
    Placeholder — real integration tests will be added once
    PostgresStorage is implemented.
    """
    assert db_url.startswith("postgresql://")
