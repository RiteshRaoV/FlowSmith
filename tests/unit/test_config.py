import pytest

import flowforge
from flowforge.exceptions import FlowForgeNotConfigured


def test_get_storage_raises_if_not_configured():
    """Flow creation should fail clearly if configure() was never called."""
    from flowforge.config import get_storage
    with pytest.raises(FlowForgeNotConfigured):
        get_storage()


def test_configure_sets_storage():
    """After configure(), get_storage() should return a backend."""
    from flowforge.config import get_storage
    flowforge.configure(database_url="postgresql://u:p@localhost/db")
    storage = get_storage()
    assert storage is not None


def test_configure_is_idempotent():
    """Calling configure() twice with the same URL should not raise."""
    flowforge.configure(database_url="postgresql://u:p@localhost/db")
    flowforge.configure(database_url="postgresql://u:p@localhost/db")  # no error


def test_configure_raises_on_different_url():
    """Calling configure() with a different URL after first call should raise."""
    flowforge.configure(database_url="postgresql://u:p@localhost/db1")
    with pytest.raises(ValueError, match="already called with a different URL"):
        flowforge.configure(database_url="postgresql://u:p@localhost/db2")


def test_reset_clears_config():
    """reset() should allow configure() to be called again cleanly."""
    flowforge.configure(database_url="postgresql://u:p@localhost/db")
    flowforge.reset()
    from flowforge.config import get_storage
    with pytest.raises(FlowForgeNotConfigured):
        get_storage()
