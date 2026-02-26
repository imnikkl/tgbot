from __future__ import annotations

import unittest

from handlers.weather_handlers import parse_alert_update_args, parse_quiet_hours_arg


class HandlerParserSmokeTests(unittest.TestCase):
    def test_parse_alert_updates_success(self) -> None:
        updates, error = parse_alert_update_args(
            "ploaie=3.5 ninsoare=2 vant=14 min=-2 max=36 cooldown=120 dimineata=on seara=off sever=on"
        )

        self.assertIsNone(error)
        self.assertEqual(updates["rain_mm_3h_threshold"], 3.5)
        self.assertEqual(updates["snow_mm_3h_threshold"], 2.0)
        self.assertEqual(updates["wind_ms_threshold"], 14.0)
        self.assertEqual(updates["min_temp_c_threshold"], -2.0)
        self.assertEqual(updates["max_temp_c_threshold"], 36.0)
        self.assertEqual(updates["alert_cooldown_minutes"], 120)
        self.assertTrue(updates["daily_morning_enabled"])
        self.assertFalse(updates["daily_evening_enabled"])
        self.assertTrue(updates["severe_immediate_enabled"])

    def test_parse_alert_updates_rejects_invalid_key(self) -> None:
        updates, error = parse_alert_update_args("foo=1")
        self.assertEqual(updates, {})
        self.assertIsNotNone(error)

    def test_parse_quiet_hours(self) -> None:
        start, end = parse_quiet_hours_arg("22:00-07:00")
        self.assertEqual(start, "22:00")
        self.assertEqual(end, "07:00")

        start_off, end_off = parse_quiet_hours_arg("off")
        self.assertIsNone(start_off)
        self.assertIsNone(end_off)

        with self.assertRaises(ValueError):
            parse_quiet_hours_arg("22:00")


if __name__ == "__main__":
    unittest.main()
