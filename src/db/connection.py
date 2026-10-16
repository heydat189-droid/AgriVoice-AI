"""AgriVoice-AI: Database Connection & Session Management.

Provides production-ready SQLite connection management with Write-Ahead Logging (WAL),
foreign keys enforcement, connection pooling context managers, and auto-migration initialization.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from src.db.migrate import DEFAULT_DB_PATH, run_migrations


def get_db_path(custom_path: Optional[Path | str] = None) -> Path:
    """Resolves target database path from parameter or environment variable."""
    if custom_path:
        return Path(custom_path)
    env_path = os.getenv("DATABASE_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def create_connection(db_path: Optional[Path | str] = None) -> sqlite3.Connection:
    """Creates a configured SQLite connection.

    Applies production SQLite pragmas:
    - foreign_keys = ON: Enforces referential integrity
    - journal_mode = WAL: High-concurrency reads and writes
    - synchronous = NORMAL: Balance between safety and performance in WAL mode
    - busy_timeout = 5000: Mitigates 'database is locked' errors under concurrent access
    """
    path = get_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(path), timeout=10.0)
    con.row_factory = sqlite3.Row

    # Enforce SQLite performance & integrity PRAGMAs
    con.execute("PRAGMA foreign_keys = ON;")
    con.execute("PRAGMA journal_mode = WAL;")
    con.execute("PRAGMA synchronous = NORMAL;")
    con.execute("PRAGMA busy_timeout = 5000;")

    return con


@contextmanager
def get_db(db_path: Optional[Path | str] = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager yielding an active database connection.

    Automatically commits on successful block exit, and rolls back on unhandled exception.
    """
    con = create_connection(db_path)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


@contextmanager
def get_cursor(db_path: Optional[Path | str] = None) -> Generator[sqlite3.Cursor, None, None]:
    """Context manager yielding a cursor from an active connection."""
    with get_db(db_path) as con:
        cur = con.cursor()
        try:
            yield cur
        finally:
            cur.close()


def initialize_database(db_path: Optional[Path | str] = None) -> int:
    """Initializes the database by running all pending migrations."""
    path = get_db_path(db_path)
    return run_migrations(db_path=path)
