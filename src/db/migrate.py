"""AgriVoice-AI: Migration Engine & CLI.

Flyway-compatible SQLite migration runner in pure Python.
Provides transactional schema migrations, version tracking, checksum verification,
and schema status reporting without external Java/Flyway dependencies.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Default database location
DEFAULT_DB_PATH = Path("data/agrivoice.db")
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migration"
HISTORY_TABLE = "flyway_schema_history"

MIGRATION_FILENAME_PATTERN = re.compile(r"^V(\d+(?:_\d+)*)__([a-zA-Z0-9_-]+)\.sql$")


@dataclass
class MigrationFile:
    version: str
    version_tuple: tuple[int, ...]
    description: str
    filename: str
    path: Path
    checksum: int

    @classmethod
    def from_path(cls, path: Path) -> Optional[MigrationFile]:
        match = MIGRATION_FILENAME_PATTERN.match(path.name)
        if not match:
            return None

        raw_version, raw_desc = match.groups()
        version_str = raw_version.replace("_", ".")
        version_tuple = tuple(int(part) for part in raw_version.split("_"))
        description = raw_desc.replace("_", " ").title()

        content = path.read_text(encoding="utf-8")
        crc = zlib.crc32(content.encode("utf-8"))
        # Match Java signed 32-bit integer
        if crc > 0x7FFFFFFF:
            crc -= 0x100000000

        return cls(
            version=version_str,
            version_tuple=version_tuple,
            description=description,
            filename=path.name,
            path=path,
            checksum=crc,
        )


@dataclass
class AppliedMigration:
    installed_rank: int
    version: str
    description: str
    script: str
    checksum: Optional[int]
    installed_by: str
    installed_on: str
    execution_time: int
    success: bool


def get_connection(db_path: Path | str) -> sqlite3.Connection:
    """Creates a configured SQLite connection with foreign keys and WAL mode."""
    target_path = Path(db_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(target_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    con.execute("PRAGMA journal_mode = WAL;")
    con.execute("PRAGMA busy_timeout = 5000;")
    return con


def ensure_history_table(con: sqlite3.Connection) -> None:
    """Ensures Flyway schema history table exists."""
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} (
            installed_rank INTEGER NOT NULL PRIMARY KEY,
            version VARCHAR(50),
            description VARCHAR(200) NOT NULL,
            type VARCHAR(20) NOT NULL,
            script VARCHAR(1000) NOT NULL,
            checksum INTEGER,
            installed_by VARCHAR(100) NOT NULL,
            installed_on TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            execution_time INTEGER NOT NULL,
            success BOOLEAN NOT NULL
        );
    """)
    con.execute(f"""
        CREATE INDEX IF NOT EXISTS {HISTORY_TABLE}_s_idx
        ON {HISTORY_TABLE} (success);
    """)
    con.commit()


def get_applied_migrations(con: sqlite3.Connection) -> List[AppliedMigration]:
    """Retrieves all migrations recorded in history table."""
    ensure_history_table(con)
    cur = con.cursor()
    cur.execute(f"""
        SELECT installed_rank, version, description, script, checksum,
               installed_by, installed_on, execution_time, success
        FROM {HISTORY_TABLE}
        ORDER BY installed_rank ASC
    """)
    rows = cur.fetchall()
    return [
        AppliedMigration(
            installed_rank=row["installed_rank"],
            version=row["version"],
            description=row["description"],
            script=row["script"],
            checksum=row["checksum"],
            installed_by=row["installed_by"],
            installed_on=row["installed_on"],
            execution_time=row["execution_time"],
            success=bool(row["success"]),
        )
        for row in rows
    ]


def load_migration_files(migrations_dir: Path = MIGRATIONS_DIR) -> List[MigrationFile]:
    """Loads and sorts all migration files in the directory."""
    if not migrations_dir.exists():
        return []

    files: List[MigrationFile] = []
    for entry in migrations_dir.iterdir():
        if entry.is_file() and entry.name.endswith(".sql"):
            m = MigrationFile.from_path(entry)
            if m:
                files.append(m)

    files.sort(key=lambda x: x.version_tuple)
    return files


def run_migrations(
    db_path: Path | str = DEFAULT_DB_PATH,
    migrations_dir: Path = MIGRATIONS_DIR,
    quiet: bool = False,
) -> int:
    """Applies pending migrations in sequential order."""
    con = get_connection(db_path)
    ensure_history_table(con)

    applied = {m.version: m for m in get_applied_migrations(con)}
    available = load_migration_files(migrations_dir)

    cur_rank = max([m.installed_rank for m in applied.values()], default=0)
    applied_count = 0

    if not quiet:
        print(f"📦 Database: {db_path}")
        print(f"📂 Migration dir: {migrations_dir}")
        print(f"🔍 Discovered {len(available)} migration files, {len(applied)} already applied.\n")

    for m in available:
        if m.version in applied:
            prev = applied[m.version]
            if not prev.success:
                raise RuntimeError(
                    f"Migration {m.version} ({m.filename}) previously failed. Resolve manually."
                )
            if prev.checksum is not None and prev.checksum != m.checksum:
                raise ValueError(
                    f"Checksum mismatch for already applied migration {m.version} ({m.filename}). "
                    f"Expected {prev.checksum}, found {m.checksum}. Never edit already applied migrations!"
                )
            continue

        if not quiet:
            print(f"🚀 Applying V{m.version}: {m.description} ({m.filename})...", end=" ", flush=True)

        sql_content = m.path.read_text(encoding="utf-8")
        cur_rank += 1
        start_time = time.perf_counter()

        try:
            # Execute migration in isolated script mode
            con.executescript(sql_content)
            exec_duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Record success in schema history
            con.execute(
                f"""
                INSERT INTO {HISTORY_TABLE} (
                    installed_rank, version, description, type, script,
                    checksum, installed_by, execution_time, success
                ) VALUES (?, ?, ?, 'SQL', ?, ?, ?, ?, 1)
                """,
                (
                    cur_rank,
                    m.version,
                    m.description,
                    m.filename,
                    m.checksum,
                    os.getenv("USER", "system"),
                    exec_duration_ms,
                ),
            )
            con.commit()
            applied_count += 1
            if not quiet:
                print(f"DONE ({exec_duration_ms}ms)")

        except Exception as err:
            exec_duration_ms = int((time.perf_counter() - start_time) * 1000)
            con.execute(
                f"""
                INSERT INTO {HISTORY_TABLE} (
                    installed_rank, version, description, type, script,
                    checksum, installed_by, execution_time, success
                ) VALUES (?, ?, ?, 'SQL', ?, ?, ?, ?, 0)
                """,
                (
                    cur_rank,
                    m.version,
                    m.description,
                    m.filename,
                    m.checksum,
                    os.getenv("USER", "system"),
                    exec_duration_ms,
                ),
            )
            con.commit()
            if not quiet:
                print(f"FAILED ({exec_duration_ms}ms)")
                print(f"❌ Error during V{m.version}: {err}", file=sys.stderr)
            raise

    # Final foreign key sanity check
    cur = con.cursor()
    cur.execute("PRAGMA foreign_key_check;")
    fk_errors = cur.fetchall()
    if fk_errors:
        raise RuntimeError(f"Foreign key integrity violation detected: {fk_errors}")

    if not quiet:
        if applied_count == 0:
            print("✅ Schema is already up to date. No pending migrations.")
        else:
            print(f"\n🎉 Successfully applied {applied_count} migration(s). Database is ready!")

    con.close()
    return applied_count


def get_migration_status(
    db_path: Path | str = DEFAULT_DB_PATH,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> None:
    """Prints migration status table (applied vs pending)."""
    con = get_connection(db_path)
    applied_map = {m.version: m for m in get_applied_migrations(con)}
    available = load_migration_files(migrations_dir)

    print(f"\n📊 Migration Status for: {db_path}")
    print("=" * 85)
    print(
        f"{'Version':<10} {'Description':<28} {'Status':<12} {'Installed On':<20} {'Duration':<10}"
    )
    print("-" * 85)

    all_versions = sorted(
        set(list(applied_map.keys()) + [m.version for m in available]),
        key=lambda v: tuple(int(p) for p in v.split(".")),
    )

    available_map = {m.version: m for m in available}

    for ver in all_versions:
        applied = applied_map.get(ver)
        file = available_map.get(ver)

        desc = (applied.description if applied else file.description) if (applied or file) else "Unknown"
        desc = (desc[:25] + "...") if len(desc) > 28 else desc

        if applied and applied.success:
            status = "SUCCESS"
            installed_on = applied.installed_on
            duration = f"{applied.execution_time}ms"
        elif applied and not applied.success:
            status = "FAILED"
            installed_on = applied.installed_on
            duration = f"{applied.execution_time}ms"
        else:
            status = "PENDING"
            installed_on = "-"
            duration = "-"

        print(f"{ver:<10} {desc:<28} {status:<12} {installed_on:<20} {duration:<10}")

    print("=" * 85)
    con.close()


def verify_checksums(
    db_path: Path | str = DEFAULT_DB_PATH,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> bool:
    """Verifies checksums of applied migrations against disk files."""
    con = get_connection(db_path)
    applied = get_applied_migrations(con)
    available = {m.version: m for m in load_migration_files(migrations_dir)}

    mismatches = 0
    for m in applied:
        disk_file = available.get(m.version)
        if not disk_file:
            print(f"⚠️  Warning: Applied migration V{m.version} not found in {migrations_dir}")
            continue

        if m.checksum is not None and m.checksum != disk_file.checksum:
            print(
                f"❌ Checksum mismatch for V{m.version}: recorded={m.checksum}, disk={disk_file.checksum}"
            )
            mismatches += 1

    con.close()
    if mismatches == 0:
        print("✅ All applied migration checksums match disk files perfectly.")
        return True
    return False


def reset_database(
    db_path: Path | str = DEFAULT_DB_PATH,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> None:
    """Deletes existing database file and re-applies all migrations."""
    target_path = Path(db_path)
    if target_path.exists():
        target_path.unlink()
        print(f"🗑️  Removed existing database: {target_path}")

    # Also clean up WAL and SHM files
    wal_file = target_path.with_name(f"{target_path.name}-wal")
    shm_file = target_path.with_name(f"{target_path.name}-shm")
    if wal_file.exists():
        wal_file.unlink()
    if shm_file.exists():
        shm_file.unlink()

    run_migrations(db_path=target_path, migrations_dir=migrations_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="AgriVoice-AI SQLite Migration Engine")
    parser.add_argument(
        "command",
        nargs="?",
        default="migrate",
        choices=["migrate", "status", "verify", "reset"],
        help="Action to execute (default: migrate)",
    )
    parser.add_argument(
        "--db",
        default=os.getenv("DATABASE_PATH", str(DEFAULT_DB_PATH)),
        help="Path to SQLite database file",
    )
    parser.add_argument(
        "--migrations-dir",
        default=str(MIGRATIONS_DIR),
        help="Directory containing migration files",
    )

    args = parser.parse_args()
    db_path = Path(args.db)
    migrations_dir = Path(args.migrations_dir)

    if args.command == "migrate":
        run_migrations(db_path=db_path, migrations_dir=migrations_dir)
    elif args.command == "status":
        get_migration_status(db_path=db_path, migrations_dir=migrations_dir)
    elif args.command == "verify":
        verify_checksums(db_path=db_path, migrations_dir=migrations_dir)
    elif args.command == "reset":
        reset_database(db_path=db_path, migrations_dir=migrations_dir)


if __name__ == "__main__":
    main()
