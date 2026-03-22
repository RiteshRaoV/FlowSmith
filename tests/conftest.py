import pytest

import flowforge
from flowforge.storage import InMemoryStorage


@pytest.fixture(autouse=True)
def reset_global_config():
    """
    Reset FlowForge global config before and after every test.
    Prevents state leaking between tests that call flowforge.configure().
    autouse=True means this runs automatically for every test.
    """
    flowforge.reset()
    yield
    flowforge.reset()


@pytest.fixture
def memory_storage() -> InMemoryStorage:
    """A fresh InMemoryStorage instance for each test."""
    return InMemoryStorage()


@pytest.fixture
def configured_memory(memory_storage):
    """
    Provides a Flow-ready environment backed by InMemoryStorage.
    Use this when testing Flow directly without calling configure().

    Example:
        def test_something(configured_memory):
            storage = configured_memory
            flow = Flow("my_flow", storage=storage)
    """
    return memory_storage
