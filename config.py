from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    bot_token: str
    weather_api_key: str | None
    location_enc_key: bytes
    db_path: str
    timezone_name: str
    cache_ttl_seconds: int
    request_timeout_seconds: float
    request_connect_timeout_seconds: float
    request_retries: int
    request_backoff_seconds: float
    morning_hour: int
    morning_minute: int
    evening_hour: int
    evening_minute: int
    severe_interval_minutes: int


def _as_required(name: str, value: str | None) -> str:
    if value is None or value.strip() == "":
        raise RuntimeError(f"Lipseste variabila obligatorie: {name}")
    return value.strip()


def _as_int(name: str, value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"Valoare invalida pentru {name}: {value}") from exc


def _as_float(name: str, value: str | None, default: float) -> float:
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError(f"Valoare invalida pentru {name}: {value}") from exc


def _decode_location_key(raw_value: str) -> bytes:
    value = raw_value.strip()

    # Prefer base64 urlsafe for easier distribution.
    padded = value + "=" * ((4 - len(value) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass

    raw_bytes = value.encode("utf-8")
    if len(raw_bytes) == 32:
        return raw_bytes

    raise RuntimeError(
        "LOCATION_ENC_KEY trebuie sa fie o cheie AES-256 valida (32 bytes), "
        "preferabil base64 urlsafe."
    )


def load_settings() -> Settings:
    load_dotenv(override=False)

    bot_token = _as_required("BOT_TOKEN", os.getenv("BOT_TOKEN"))
    location_key_raw = _as_required("LOCATION_ENC_KEY", os.getenv("LOCATION_ENC_KEY"))

    weather_api_key = os.getenv("WEATHER_API_KEY")
    if not weather_api_key:
        LOGGER.warning(
            "WEATHER_API_KEY nu este setata. OpenWeather va fi omis, fallback la Open-Meteo."
        )

    return Settings(
        bot_token=bot_token,
        weather_api_key=weather_api_key.strip() if weather_api_key else None,
        location_enc_key=_decode_location_key(location_key_raw),
        db_path=os.getenv("DB_PATH", "weather_bot.db"),
        timezone_name=os.getenv("APP_TIMEZONE", "Europe/Bucharest"),
        cache_ttl_seconds=_as_int("CACHE_TTL_SECONDS", os.getenv("CACHE_TTL_SECONDS"), 600),
        request_timeout_seconds=_as_float("REQUEST_TIMEOUT_SECONDS", os.getenv("REQUEST_TIMEOUT_SECONDS"), 10.0),
        request_connect_timeout_seconds=_as_float(
            "REQUEST_CONNECT_TIMEOUT_SECONDS",
            os.getenv("REQUEST_CONNECT_TIMEOUT_SECONDS"),
            4.0,
        ),
        request_retries=_as_int("REQUEST_RETRIES", os.getenv("REQUEST_RETRIES"), 3),
        request_backoff_seconds=_as_float("REQUEST_BACKOFF_SECONDS", os.getenv("REQUEST_BACKOFF_SECONDS"), 0.8),
        morning_hour=_as_int("ALERT_MORNING_HOUR", os.getenv("ALERT_MORNING_HOUR"), 7),
        morning_minute=_as_int("ALERT_MORNING_MINUTE", os.getenv("ALERT_MORNING_MINUTE"), 30),
        evening_hour=_as_int("ALERT_EVENING_HOUR", os.getenv("ALERT_EVENING_HOUR"), 19),
        evening_minute=_as_int("ALERT_EVENING_MINUTE", os.getenv("ALERT_EVENING_MINUTE"), 30),
        severe_interval_minutes=_as_int(
            "SEVERE_INTERVAL_MINUTES",
            os.getenv("SEVERE_INTERVAL_MINUTES"),
            30,
        ),
    )
