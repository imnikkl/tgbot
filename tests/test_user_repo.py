from __future__ import annotations

import struct
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from database import EncryptedFloat
from migrations.runner import run_migrations
from repositories.user_repo import UserRepository


class _FakeCipher:
    def encrypt_float(self, value: float) -> EncryptedFloat:
        return EncryptedFloat(ciphertext=struct.pack(">d", float(value)), nonce=b"fixed_nonce01")

    def decrypt_float(self, encrypted: EncryptedFloat) -> float:
        return struct.unpack(">d", encrypted.ciphertext)[0]


class UserRepoTests(unittest.IsolatedAsyncioTestCase):
    async def test_alert_cooldown_and_mark_sent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "repo.db"
            await run_migrations(str(db_path))

            repo = UserRepository(str(db_path), _FakeCipher())
            await repo.upsert_user_location(user_id=1, chat_id=11, latitude=44.4, longitude=26.1)

            now = datetime.now(timezone.utc)
            key = "rain:2026010109:normal"

            recently_before = await repo.was_alert_sent_recently(1, key, 180, now)
            self.assertFalse(recently_before)

            await repo.mark_alert_sent(1, key, now)

            recently_after = await repo.was_alert_sent_recently(1, key, 180, now)
            self.assertTrue(recently_after)

            future = now + timedelta(minutes=181)
            recently_after_window = await repo.was_alert_sent_recently(1, key, 180, future)
            self.assertFalse(recently_after_window)


if __name__ == "__main__":
    unittest.main()
