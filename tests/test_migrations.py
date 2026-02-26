from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import aiosqlite

from migrations.runner import run_migrations


class MigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_migrations_are_idempotent_and_keep_users(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"

            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    """
                    CREATE TABLE users (
                        user_id INTEGER PRIMARY KEY,
                        chat_id INTEGER NOT NULL,
                        latitude REAL NOT NULL,
                        longitude REAL NOT NULL
                    )
                    """
                )
                await db.execute(
                    "INSERT INTO users (user_id, chat_id, latitude, longitude) VALUES (1, 10, 44.4, 26.1)"
                )
                await db.commit()

            await run_migrations(str(db_path))
            await run_migrations(str(db_path))

            async with aiosqlite.connect(db_path) as db:
                async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                    users_count = (await cursor.fetchone())[0]
                async with db.execute("SELECT COUNT(*) FROM alert_rules") as cursor:
                    rules_count = (await cursor.fetchone())[0]
                async with db.execute(
                    "SELECT COUNT(*) FROM schema_migrations WHERE id = '001_init_v2'"
                ) as cursor:
                    migration_rows = (await cursor.fetchone())[0]

            self.assertEqual(users_count, 1)
            self.assertEqual(rules_count, 1)
            self.assertEqual(migration_rows, 1)


if __name__ == "__main__":
    unittest.main()
