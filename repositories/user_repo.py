from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import aiosqlite

from database import AesGcmCoordinateCipher, EncryptedFloat


LOGGER = logging.getLogger(__name__)


DEFAULT_RULES = {
    "rain_mm_3h_threshold": 2.0,
    "snow_mm_3h_threshold": 1.0,
    "wind_ms_threshold": 13.0,
    "min_temp_c_threshold": 0.0,
    "max_temp_c_threshold": 35.0,
}


class UserRepository:
    def __init__(self, db_path: str, cipher: AesGcmCoordinateCipher):
        self._db_path = db_path
        self._cipher = cipher

    async def upsert_user_location(
        self,
        user_id: int,
        chat_id: int,
        latitude: float,
        longitude: float,
    ) -> None:
        encrypted_lat = self._cipher.encrypt_float(latitude)
        encrypted_lon = self._cipher.encrypt_float(longitude)

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO users (
                    user_id,
                    chat_id,
                    latitude,
                    longitude,
                    enc_latitude,
                    enc_longitude,
                    lat_nonce,
                    lon_nonce
                )
                VALUES (?, ?, 0, 0, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    chat_id = excluded.chat_id,
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    enc_latitude = excluded.enc_latitude,
                    enc_longitude = excluded.enc_longitude,
                    lat_nonce = excluded.lat_nonce,
                    lon_nonce = excluded.lon_nonce
                """,
                (
                    user_id,
                    chat_id,
                    encrypted_lat.ciphertext,
                    encrypted_lon.ciphertext,
                    encrypted_lat.nonce,
                    encrypted_lon.nonce,
                ),
            )
            await db.execute(
                """
                INSERT OR IGNORE INTO alert_rules (user_id)
                VALUES (?)
                """,
                (user_id,),
            )
            await db.commit()

    async def get_user(self, user_id: int) -> dict | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT
                    u.*,
                    ar.rain_mm_3h_threshold,
                    ar.snow_mm_3h_threshold,
                    ar.wind_ms_threshold,
                    ar.min_temp_c_threshold,
                    ar.max_temp_c_threshold
                FROM users u
                LEFT JOIN alert_rules ar ON ar.user_id = u.user_id
                WHERE u.user_id = ?
                """,
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if row is None:
            return None

        data = dict(row)
        return self._normalize_user_row(data)

    async def get_all_users(self) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT
                    u.*,
                    ar.rain_mm_3h_threshold,
                    ar.snow_mm_3h_threshold,
                    ar.wind_ms_threshold,
                    ar.min_temp_c_threshold,
                    ar.max_temp_c_threshold
                FROM users u
                LEFT JOIN alert_rules ar ON ar.user_id = u.user_id
                """
            ) as cursor:
                rows = await cursor.fetchall()

        return [self._normalize_user_row(dict(row)) for row in rows]

    async def update_quiet_hours(
        self,
        user_id: int,
        quiet_start: str | None,
        quiet_end: str | None,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                UPDATE users
                SET quiet_start = ?, quiet_end = ?
                WHERE user_id = ?
                """,
                (quiet_start, quiet_end, user_id),
            )
            await db.commit()

    async def update_alert_preferences(
        self,
        user_id: int,
        *,
        rain_mm_3h_threshold: float | None = None,
        snow_mm_3h_threshold: float | None = None,
        wind_ms_threshold: float | None = None,
        min_temp_c_threshold: float | None = None,
        max_temp_c_threshold: float | None = None,
        alert_cooldown_minutes: int | None = None,
        daily_morning_enabled: bool | None = None,
        daily_evening_enabled: bool | None = None,
        severe_immediate_enabled: bool | None = None,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO alert_rules (user_id) VALUES (?)",
                (user_id,),
            )

            alert_updates: list[str] = []
            alert_values: list[float] = []
            user_updates: list[str] = []
            user_values: list[int] = []

            if rain_mm_3h_threshold is not None:
                alert_updates.append("rain_mm_3h_threshold = ?")
                alert_values.append(float(rain_mm_3h_threshold))
            if snow_mm_3h_threshold is not None:
                alert_updates.append("snow_mm_3h_threshold = ?")
                alert_values.append(float(snow_mm_3h_threshold))
            if wind_ms_threshold is not None:
                alert_updates.append("wind_ms_threshold = ?")
                alert_values.append(float(wind_ms_threshold))
            if min_temp_c_threshold is not None:
                alert_updates.append("min_temp_c_threshold = ?")
                alert_values.append(float(min_temp_c_threshold))
            if max_temp_c_threshold is not None:
                alert_updates.append("max_temp_c_threshold = ?")
                alert_values.append(float(max_temp_c_threshold))

            if alert_cooldown_minutes is not None:
                user_updates.append("alert_cooldown_minutes = ?")
                user_values.append(int(alert_cooldown_minutes))
            if daily_morning_enabled is not None:
                user_updates.append("daily_morning_enabled = ?")
                user_values.append(1 if daily_morning_enabled else 0)
            if daily_evening_enabled is not None:
                user_updates.append("daily_evening_enabled = ?")
                user_values.append(1 if daily_evening_enabled else 0)
            if severe_immediate_enabled is not None:
                user_updates.append("severe_immediate_enabled = ?")
                user_values.append(1 if severe_immediate_enabled else 0)

            if alert_updates:
                query = f"UPDATE alert_rules SET {', '.join(alert_updates)} WHERE user_id = ?"
                await db.execute(query, (*alert_values, user_id))

            if user_updates:
                query = f"UPDATE users SET {', '.join(user_updates)} WHERE user_id = ?"
                await db.execute(query, (*user_values, user_id))

            await db.commit()

    async def was_alert_sent_recently(
        self,
        user_id: int,
        event_key: str,
        cooldown_minutes: int,
        now_utc: datetime,
    ) -> bool:
        cutoff = now_utc - timedelta(minutes=cooldown_minutes)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT sent_at_utc
                FROM sent_alerts
                WHERE user_id = ? AND event_key = ?
                """,
                (user_id, event_key),
            ) as cursor:
                row = await cursor.fetchone()

        if row is None:
            return False

        sent_at = datetime.fromisoformat(row["sent_at_utc"])
        return sent_at >= cutoff

    async def mark_alert_sent(self, user_id: int, event_key: str, now_utc: datetime) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO sent_alerts (user_id, event_key, sent_at_utc)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, event_key) DO UPDATE SET
                    sent_at_utc = excluded.sent_at_utc
                """,
                (user_id, event_key, now_utc.isoformat(timespec="seconds")),
            )
            await db.commit()

    async def cleanup_old_alerts(self, retention_days: int = 14) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "DELETE FROM sent_alerts WHERE sent_at_utc < ?",
                (cutoff.isoformat(timespec="seconds"),),
            )
            await db.commit()

    async def migrate_plain_coordinates(self) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT user_id, latitude, longitude
                FROM users
                WHERE (enc_latitude IS NULL OR lat_nonce IS NULL)
                   OR (enc_longitude IS NULL OR lon_nonce IS NULL)
                """
            ) as cursor:
                rows = await cursor.fetchall()

            migrated = 0
            for row in rows:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
                encrypted_lat = self._cipher.encrypt_float(lat)
                encrypted_lon = self._cipher.encrypt_float(lon)
                await db.execute(
                    """
                    UPDATE users
                    SET
                        enc_latitude = ?,
                        enc_longitude = ?,
                        lat_nonce = ?,
                        lon_nonce = ?,
                        latitude = 0,
                        longitude = 0
                    WHERE user_id = ?
                    """,
                    (
                        encrypted_lat.ciphertext,
                        encrypted_lon.ciphertext,
                        encrypted_lat.nonce,
                        encrypted_lon.nonce,
                        row["user_id"],
                    ),
                )
                await db.execute(
                    "INSERT OR IGNORE INTO alert_rules (user_id) VALUES (?)",
                    (row["user_id"],),
                )
                migrated += 1

            await db.commit()

        return migrated

    def _normalize_user_row(self, row: dict) -> dict:
        latitude = row.get("latitude")
        longitude = row.get("longitude")

        if row.get("enc_latitude") and row.get("lat_nonce"):
            latitude = self._cipher.decrypt_float(
                EncryptedFloat(
                    ciphertext=row["enc_latitude"],
                    nonce=row["lat_nonce"],
                )
            )
        if row.get("enc_longitude") and row.get("lon_nonce"):
            longitude = self._cipher.decrypt_float(
                EncryptedFloat(
                    ciphertext=row["enc_longitude"],
                    nonce=row["lon_nonce"],
                )
            )

        row["latitude"] = float(latitude)
        row["longitude"] = float(longitude)

        for key, value in DEFAULT_RULES.items():
            if row.get(key) is None:
                row[key] = value

        row["daily_morning_enabled"] = int(row.get("daily_morning_enabled", 1))
        row["daily_evening_enabled"] = int(row.get("daily_evening_enabled", 1))
        row["severe_immediate_enabled"] = int(row.get("severe_immediate_enabled", 1))
        row["alert_cooldown_minutes"] = int(row.get("alert_cooldown_minutes", 180))

        if not row.get("timezone"):
            row["timezone"] = "Europe/Bucharest"
        if not row.get("locale"):
            row["locale"] = "ro"
        if not row.get("units"):
            row["units"] = "metric"

        return row
