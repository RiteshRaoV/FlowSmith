import pytest

import flowsmith
from flowsmith.exceptions import FlowSmithNotConfigured


def test_get_storage_raises_if_not_configured():
    """Flow creation should fail clearly if configure() was never called."""
    from flowsmith.config import get_storage
    with pytest.raises(FlowSmithNotConfigured):
        get_storage()


def test_configure_sets_storage():
    """After configure(), get_storage() should return a backend."""
    from flowsmith.config import get_storage
    flowsmith.configure(database_url="postgresql://u:p@localhost/db")
    storage = get_storage()
    assert storage is not None


def test_configure_is_idempotent():
    """Calling configure() twice with the same URL should not raise."""
    flowsmith.configure(database_url="postgresql://u:p@localhost/db")
    flowsmith.configure(database_url="postgresql://u:p@localhost/db")  # no error


def test_configure_raises_on_different_url():
    """Calling configure() with a different URL after first call should raise."""
    flowsmith.configure(database_url="postgresql://u:p@localhost/db1")
    with pytest.raises(ValueError, match="already called with a different URL"):
        flowsmith.configure(database_url="postgresql://u:p@localhost/db2")


def test_reset_clears_config():
    """reset() should allow configure() to be called again cleanly."""
    flowsmith.configure(database_url="postgresql://u:p@localhost/db")
    flowsmith.reset()
    from flowsmith.config import get_storage
    with pytest.raises(FlowSmithNotConfigured):
        get_storage()
