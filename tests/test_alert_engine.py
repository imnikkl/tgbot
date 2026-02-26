from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from services.alert_engine import AlertEngine
from services.models import NormalizedForecast, UserAlertPrefs, WeatherPoint


class AlertEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = AlertEngine()
        self.now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    def _forecast(self) -> NormalizedForecast:
        points = [
            WeatherPoint(
                dt_utc=self.now + timedelta(hours=2),
                temp_c=-12.0,
                feels_like_c=-15.0,
                condition_main="Snow",
                description="ninsoare",
                humidity_percent=90,
                wind_ms=18.0,
                rain_mm_3h=0.0,
                snow_mm_3h=9.0,
            ),
            WeatherPoint(
                dt_utc=self.now + timedelta(hours=4),
                temp_c=36.0,
                feels_like_c=38.0,
                condition_main="Rain",
                description="ploaie",
                humidity_percent=80,
                wind_ms=12.0,
                rain_mm_3h=4.0,
                snow_mm_3h=0.0,
            ),
        ]
        return NormalizedForecast(
            city_name="Bucuresti",
            timezone_offset_seconds=2 * 3600,
            sunrise_utc=None,
            sunset_utc=None,
            points=points,
            provider_name="openweather",
            fetched_at_utc=self.now,
        )

    def test_evaluate_events_respects_thresholds_and_severity(self) -> None:
        forecast = self._forecast()
        prefs = UserAlertPrefs(
            rain_mm_3h_threshold=2.0,
            snow_mm_3h_threshold=1.0,
            wind_ms_threshold=13.0,
            min_temp_c_threshold=0.0,
            max_temp_c_threshold=35.0,
        )

        events = self.engine.evaluate_events(
            forecast,
            prefs,
            now_utc=self.now,
            hours=24,
            severe_only=False,
        )

        event_types = {event.event_type for event in events}
        self.assertTrue({"snow", "wind", "cold", "rain", "heat"}.issubset(event_types))

        severe_events = [event for event in events if event.severity == "severe"]
        self.assertTrue(any(event.event_type == "cold" for event in severe_events))
        self.assertTrue(any(event.event_type == "wind" for event in severe_events))

    def test_quiet_hours_overnight(self) -> None:
        # 22:00-07:00 local, UTC+2. 21:30 UTC => 23:30 local => quiet true.
        now_utc = datetime(2026, 1, 10, 21, 30, tzinfo=timezone.utc)
        quiet = self.engine.is_quiet_now(now_utc, 2 * 3600, "22:00", "07:00")
        self.assertTrue(quiet)

        # 12:00 UTC => 14:00 local => quiet false.
        now_utc_day = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        quiet_day = self.engine.is_quiet_now(now_utc_day, 2 * 3600, "22:00", "07:00")
        self.assertFalse(quiet_day)


if __name__ == "__main__":
    unittest.main()
