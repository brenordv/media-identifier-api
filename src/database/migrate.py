"""Command line entry point that applies pending migrations: ``uv run python -m src.database.migrate``.

Database settings come from the ``POSTGRES_*`` environment variables (or ``.env``).
"""

import sys

import psycopg
from dotenv import load_dotenv

from src.database.migrations import MigrationError, apply_migrations
from src.database.pool import build_conninfo
from src.utils import get_otel_log_handler


def main() -> int:
    """Apply pending migrations to the configured database.

    Returns:
        0 when the schema is current, 1 when the settings are incomplete or a migration fails.
    """
    load_dotenv()

    try:
        logger = get_otel_log_handler("Migrations")
        applied = apply_migrations(build_conninfo(), logger)
    except (ValueError, MigrationError, psycopg.Error) as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1

    if applied:
        print(f"Applied {len(applied)} migration(s): {', '.join(migration.label for migration in applied)}")
    else:
        print("Database schema is up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
