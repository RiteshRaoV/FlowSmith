import threading
from typing import Any

from flowsmith.exceptions import FlowSmithNotConfigured
from flowsmith.storage.base import StorageBackend

_lock = threading.Lock()
_storage: StorageBackend | None = None
_watchdog: Any = None


def _make_storage(
    database_url: str,
    pool_min: int,
    pool_max: int,
    pool_timeout: int,
) -> StorageBackend:
    """
    Instantiate the correct backend from the database URL scheme.
    All pool params are passed through to the backend.
    """
    if database_url.startswith("postgresql://") or database_url.startswith("postgres://"):
        from flowsmith.storage.postgres import PostgresStorage
        return PostgresStorage(url=database_url, pool_min=pool_min, pool_max=pool_max, pool_timeout=pool_timeout)

    if database_url.startswith("mysql://"):
        from flowsmith.storage.mysql import MySQLStorage
        return MySQLStorage(url=database_url, pool_min=pool_min, pool_max=pool_max, pool_timeout=pool_timeout)

    raise ValueError(
        f"Unsupported database URL scheme: '{database_url.split('://')[0]}'\n"
        "Supported: postgresql://, postgres://, mysql://"
    )


def configure(
    database_url: str,
    pool_min: int = 2,
    pool_max: int = 10,
    pool_timeout: int = 30,
) -> None:
    """
    Initialise FlowSmith with a database URL and connection pool settings.
    Call once at server startup.

    Args:
        database_url: PostgreSQL or MySQL connection string.
                      postgresql://user:password@host:port/dbname
                      mysql://user:password@host:port/dbname
        pool_min:     Minimum connections kept alive in the pool. Default 2.
        pool_max:     Maximum connections in the pool. Default 10.
        pool_timeout: Seconds to wait for a connection before raising. Default 30.

    Thread-safe and idempotent — calling again with the same URL is a no-op.
    Raises ValueError if called again with a different URL.
    """
    global _storage

    with _lock:
        if _storage is not None:
            existing_url = getattr(_storage, "_url", None)
            if existing_url != database_url:
                raise ValueError(
                    "flowsmith.configure() was already called with a different URL. "
                    "Call flowsmith.reset() first (test environments only)."
                )
            return

        _storage = _make_storage(database_url, pool_min, pool_max, pool_timeout)


def start_watchdog(
    timeout_seconds: int = 300,
    interval_seconds: int = 60,
) -> None:
    """
    Start the background watchdog that detects stuck nodes.

    Call this after flowsmith.configure() at server startup.

    Args:
        timeout_seconds: How long a node can stay in RUNNING before it is
                         considered stuck. Default 300s (5 minutes).
        interval_seconds: How often the watchdog scans for stuck nodes.
                          Default 60s (1 minute).

    Example:
        import flowsmith
        flowsmith.configure(database_url=os.environ["DATABASE_URL"])
        flowsmith.start_watchdog(timeout_seconds=300, interval_seconds=60)
    """
    global _watchdog

    storage = get_storage()   # raises FlowSmithNotConfigured if not configured

    with _lock:
        if _watchdog and _watchdog.is_running:
            return  # already running, no-op

        from flowsmith.watchdog import Watchdog
        _watchdog = Watchdog(
            storage=storage,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        )
        _watchdog.start()


def stop_watchdog() -> None:
    """
    Stop the watchdog thread. Blocks until the thread exits.
    Useful for clean shutdown in tests or long-running processes.
    """
    global _watchdog
    if _watchdog and _watchdog.is_running:
        _watchdog.stop()
        _watchdog = None


def get_storage() -> StorageBackend:
    """
    Return the globally configured storage backend.
    Raises FlowSmithNotConfigured if configure() has not been called.
    """
    if _storage is None:
        raise FlowSmithNotConfigured()
    return _storage


def reset() -> None:
    """Reset global config and stop watchdog. FOR TESTING ONLY."""
    global _storage, _watchdog
    with _lock:
        if _watchdog and _watchdog.is_running:
            _watchdog.stop()
        _watchdog = None
        _storage = None
