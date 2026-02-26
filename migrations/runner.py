from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite


LOGGER = logging.getLogger(__name__)

MIGRATION_ID = "001_init_v2"

USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    latitude REAL NOT NULL DEFAULT 0,
    longitude REAL NOT NULL DEFAULT 0,
    timezone TEXT NOT NULL DEFAULT 'Europe/Bucharest',
    locale TEXT NOT NULL DEFAULT 'ro',
    units TEXT NOT NULL DEFAULT 'metric',
    quiet_start TEXT NULL,
    quiet_end TEXT NULL,
    daily_morning_enabled INTEGER NOT NULL DEFAULT 1,
    daily_evening_enabled INTEGER NOT NULL DEFAULT 1,
    severe_immediate_enabled INTEGER NOT NULL DEFAULT 1,
    alert_cooldown_minutes INTEGER NOT NULL DEFAULT 180,
    enc_latitude BLOB NULL,
    enc_longitude BLOB NULL,
    lat_nonce BLOB NULL,
    lon_nonce BLOB NULL
);
"""

USERS_COLUMNS = {
    "timezone": "TEXT NOT NULL DEFAULT 'Europe/Bucharest'",
    "locale": "TEXT NOT NULL DEFAULT 'ro'",
    "units": "TEXT NOT NULL DEFAULT 'metric'",
    "quiet_start": "TEXT NULL",
    "quiet_end": "TEXT NULL",
    "daily_morning_enabled": "INTEGER NOT NULL DEFAULT 1",
    "daily_evening_enabled": "INTEGER NOT NULL DEFAULT 1",
    "severe_immediate_enabled": "INTEGER NOT NULL DEFAULT 1",
    "alert_cooldown_minutes": "INTEGER NOT NULL DEFAULT 180",
    "enc_latitude": "BLOB NULL",
    "enc_longitude": "BLOB NULL",
    "lat_nonce": "BLOB NULL",
    "lon_nonce": "BLOB NULL",
}


async def _column_names(db: aiosqlite.Connection, table_name: str) -> set[str]:
    async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
        rows = await cursor.fetchall()
    return {str(row[1]) for row in rows}


async def _ensure_users_table(db: aiosqlite.Connection) -> None:
    await db.execute(USERS_TABLE_SQL)
    existing_columns = await _column_names(db, "users")

    for column_name, column_def in USERS_COLUMNS.items():
        if column_name in existing_columns:
            continue
        await db.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_def}")
        LOGGER.info("Added users column", extra={"column": column_name})


async def _ensure_alert_rule_defaults(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        INSERT OR IGNORE INTO alert_rules (user_id)
        SELECT user_id FROM users
        """
    )


async def run_migrations(db_path: str) -> None:
    script_path = Path(__file__).with_name("001_init_v2.sql")
    sql_script = script_path.read_text(encoding="utf-8")

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await _ensure_users_table(db)
        await db.executescript(sql_script)
        await _ensure_alert_rule_defaults(db)
        await db.execute(
            """
            INSERT OR IGNORE INTO schema_migrations (id, applied_at_utc)
            VALUES (?, ?)
            """,
            (MIGRATION_ID, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        await db.commit()

    LOGGER.info("Migrations completed", extra={"migration": MIGRATION_ID})
