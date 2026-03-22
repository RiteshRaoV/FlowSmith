import threading
from typing import Optional

from flowforge.exceptions import FlowForgeNotConfigured
from flowforge.storage.base import StorageBackend
from flowforge.storage.postgres import PostgresStorage

_lock = threading.Lock()
_storage: Optional[StorageBackend] = None


def configure(database_url: str) -> None:
    """
    Initialise FlowForge with a PostgreSQL database URL.
    Call this once at server startup — e.g. in app.py, main.py,
    or Django's AppConfig.ready().

    Args:
        database_url: A full PostgreSQL connection string.
                      Format: postgresql://user:password@host:port/dbname

    Example:
        import flowforge
        flowforge.configure(database_url=os.environ["DATABASE_URL"])

    Thread-safe: safe to call from any startup context.
    Idempotent: calling it a second time with the same URL is a no-op.
    Raises ValueError if called again with a different URL.
    """
    global _storage

    with _lock:
        if _storage is not None:
            # Already configured — validate it's the same URL
            existing_url = getattr(_storage, "_url", None)
            if existing_url != database_url:
                raise ValueError(
                    "flowforge.configure() was already called with a different URL. "
                    "To reconfigure, call flowforge.reset() first (test environments only)."
                )
            return  # idempotent — same URL, no-op

        _storage = PostgresStorage(url=database_url)


def get_storage() -> StorageBackend:
    """
    Return the globally configured storage backend.
    Called internally by Flow when no local storage override is provided.

    Raises:
        FlowForgeNotConfigured: if configure() has not been called yet.
    """
    if _storage is None:
        raise FlowForgeNotConfigured()
    return _storage


def reset() -> None:
    """
    Reset global configuration. FOR TESTING ONLY.
    Never call this in production code.
    """
    global _storage
    with _lock:
        _storage = None
