"""
FlowForge CLI
Usage:
    flowforge migrate --url postgresql://user:pass@localhost/db
    flowforge migrate --url mysql://user:pass@localhost/db
    flowforge migrate  # reads DATABASE_URL from environment
    flowforge migrate  # reads DATABASE_URL from environment
"""

import argparse
import os
import sys
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def detect_dialect(url: str) -> str:
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return "postgres"
    if url.startswith("mysql://"):
        return "mysql"
    raise ValueError(
        f"Unsupported database URL scheme: '{url.split('://')[0]}'\n"
        "Supported schemes: postgresql://, postgres://, mysql://"
    )


def run_migrations_postgres(url: str) -> None:
    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 is required for PostgreSQL.")
        print("Install it with:  pip install flowforge[postgres]")
        sys.exit(1)

    migration_dir = MIGRATIONS_DIR / "postgres"
    sql_files = sorted(migration_dir.glob("*.sql"))

    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()

    for sql_file in sql_files:
        print(f"  -> {sql_file.name}")
        cur.execute(sql_file.read_text())

    cur.close()
    conn.close()


def _split_mysql_statements(sql: str) -> list[str]:
    """
    Split a MySQL SQL file into individual executable statements.

    Naive semicolon splitting breaks BEGIN...END blocks used in stored
    procedures — each internal statement ends with a semicolon but must
    be sent to MySQL as part of the whole CREATE PROCEDURE block.

    This parser tracks BEGIN/END nesting depth and only splits on
    semicolons that appear outside of a BEGIN...END block.
    """
    statements = []
    current = []
    depth = 0

    for line in sql.splitlines():
        stripped = line.strip().upper()

        if stripped in ("BEGIN", "BEGIN;"):
            depth += 1
        elif stripped in ("END", "END;", "END;"):
            depth -= 1

        current.append(line)

        if stripped.endswith(";") and depth == 0:
            stmt = "\n".join(current).strip().rstrip(";")
            if stmt:
                statements.append(stmt)
            current = []

    remainder = "\n".join(current).strip()
    if remainder:
        statements.append(remainder)

    return statements


def run_migrations_mysql(url: str) -> None:
    try:
        import mysql.connector
    except ImportError:
        print("ERROR: mysql-connector-python is required for MySQL.")
        print("Install it with:  pip install flowforge[mysql]")
        sys.exit(1)

    from urllib.parse import urlparse
    parsed = urlparse(url)

    migration_dir = MIGRATIONS_DIR / "mysql"
    sql_files = sorted(migration_dir.glob("*.sql"))

    conn = mysql.connector.connect(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip("/"),
    )
    cur = conn.cursor()

    for sql_file in sql_files:
        print(f"  -> {sql_file.name}")
        statements = _split_mysql_statements(sql_file.read_text())
        for stmt in statements:
            if stmt:
                cur.execute(stmt)

    conn.commit()
    cur.close()
    conn.close()


def cmd_migrate(args: argparse.Namespace) -> None:
    url = args.url or os.environ.get("DATABASE_URL")

    if not url:
        print(
            "ERROR: No database URL provided.\n"
            "Pass --url or set the DATABASE_URL environment variable.\n\n"
            "Examples:\n"
            "  flowforge migrate --url postgresql://user:pass@localhost/mydb\n"
            "  flowforge migrate --url mysql://user:pass@localhost/mydb\n"
        )
        sys.exit(1)

    try:
        dialect = detect_dialect(url)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"Running FlowForge migrations ({dialect})...")

    try:
        if dialect == "postgres":
            run_migrations_postgres(url)
        elif dialect == "mysql":
            run_migrations_mysql(url)
    except Exception as e:
        print(f"\nERROR: Migration failed: {e}")
        sys.exit(1)

    print("Done. Tables ff_flows and ff_nodes are ready.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="flowforge",
        description="FlowForge CLI",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Core
    migrate_parser = subparsers.add_parser("migrate", help="Run database migrations")
    migrate_parser.add_argument("--url", help="Database URL", default=None)

    args = parser.parse_args()

    if args.command == "migrate":
        cmd_migrate(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()