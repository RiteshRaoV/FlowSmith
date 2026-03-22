import threading
from typing import Optional

from flowforge.exceptions import FlowForgeNotConfigured
from flowforge.storage.base import StorageBackend

_lock = threading.Lock()
_storage: Optional[StorageBackend] = None
_watchdog = None   # type: ignore


def _make_storage(database_url: str) -> StorageBackend:
    if database_url.startswith("postgresql://") or database_url.startswith("postgres://"):
        from flowforge.storage.postgres import PostgresStorage
        return PostgresStorage(url=database_url)

    if database_url.startswith("mysql://"):
        from flowforge.storage.mysql import MySQLStorage
        return MySQLStorage(url=database_url)

    raise ValueError(
        f"Unsupported database URL scheme: '{database_url.split('://')[0]}'\n"
        "Supported: postgresql://, postgres://, mysql://"
    )


def configure(database_url: str) -> None:
    """
    Initialise FlowForge with a database URL.
    Call once at server startup.

    Supports:
        postgresql://user:password@host:port/dbname
        mysql://user:password@host:port/dbname

    Thread-safe and idempotent — calling again with the same URL is a no-op.
    Raises ValueError if called again with a different URL.
    """
    global _storage

    with _lock:
        if _storage is not None:
            existing_url = getattr(_storage, "_url", None)
            if existing_url != database_url:
                raise ValueError(
                    "flowforge.configure() was already called with a different URL. "
                    "Call flowforge.reset() first (test environments only)."
                )
            return

        _storage = _make_storage(database_url)


def start_watchdog(
    timeout_seconds: int = 300,
    interval_seconds: int = 60,
) -> None:
    """
    Start the background watchdog that detects stuck nodes.

    Call this after flowforge.configure() at server startup.

    Args:
        timeout_seconds: How long a node can stay in RUNNING before it is
                         considered stuck. Default 300s (5 minutes).
        interval_seconds: How often the watchdog scans for stuck nodes.
                          Default 60s (1 minute).

    Example:
        import flowforge
        flowforge.configure(database_url=os.environ["DATABASE_URL"])
        flowforge.start_watchdog(timeout_seconds=300, interval_seconds=60)
    """
    global _watchdog

    storage = get_storage()   # raises FlowForgeNotConfigured if not configured

    with _lock:
        if _watchdog and _watchdog.is_running:
            return  # already running, no-op

        from flowforge.watchdog import Watchdog
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
    Raises FlowForgeNotConfigured if configure() has not been called.
    """
    if _storage is None:
        raise FlowForgeNotConfigured()
    return _storage


def reset() -> None:
    """Reset global config and stop watchdog. FOR TESTING ONLY."""
    global _storage, _watchdog
    with _lock:
        if _watchdog and _watchdog.is_running:
            _watchdog.stop()
        _watchdog = None
        _storage = None
