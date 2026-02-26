from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class WeatherPoint:
    dt_utc: datetime
    temp_c: float
    feels_like_c: float
    condition_main: str
    description: str
    humidity_percent: float
    wind_ms: float
    rain_mm_3h: float
    snow_mm_3h: float


@dataclass(slots=True)
class NormalizedForecast:
    city_name: str
    timezone_offset_seconds: int
    sunrise_utc: datetime | None
    sunset_utc: datetime | None
    points: list[WeatherPoint]
    provider_name: str
    fetched_at_utc: datetime


@dataclass(slots=True)
class AlertEvent:
    event_key: str
    event_type: str
    severity: str
    starts_at_utc: datetime
    title: str
    message: str


@dataclass(slots=True)
class UserAlertPrefs:
    rain_mm_3h_threshold: float = 2.0
    snow_mm_3h_threshold: float = 1.0
    wind_ms_threshold: float = 13.0
    min_temp_c_threshold: float = 0.0
    max_temp_c_threshold: float = 35.0
    quiet_start: str | None = None
    quiet_end: str | None = None
    daily_morning_enabled: bool = True
    daily_evening_enabled: bool = True
    severe_immediate_enabled: bool = True
    alert_cooldown_minutes: int = 180
