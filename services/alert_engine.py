from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Iterable

from services.models import AlertEvent, NormalizedForecast, UserAlertPrefs, WeatherPoint


class AlertEngine:
    def __init__(
        self,
        *,
        severe_min_temp_c: float = -10.0,
        severe_max_temp_c: float = 38.0,
        severe_wind_ms: float = 17.0,
    ):
        self._severe_min_temp_c = severe_min_temp_c
        self._severe_max_temp_c = severe_max_temp_c
        self._severe_wind_ms = severe_wind_ms

    @staticmethod
    def prefs_from_user(user: dict) -> UserAlertPrefs:
        return UserAlertPrefs(
            rain_mm_3h_threshold=float(user.get("rain_mm_3h_threshold", 2.0)),
            snow_mm_3h_threshold=float(user.get("snow_mm_3h_threshold", 1.0)),
            wind_ms_threshold=float(user.get("wind_ms_threshold", 13.0)),
            min_temp_c_threshold=float(user.get("min_temp_c_threshold", 0.0)),
            max_temp_c_threshold=float(user.get("max_temp_c_threshold", 35.0)),
            quiet_start=user.get("quiet_start"),
            quiet_end=user.get("quiet_end"),
            daily_morning_enabled=bool(user.get("daily_morning_enabled", 1)),
            daily_evening_enabled=bool(user.get("daily_evening_enabled", 1)),
            severe_immediate_enabled=bool(user.get("severe_immediate_enabled", 1)),
            alert_cooldown_minutes=int(user.get("alert_cooldown_minutes", 180)),
        )

    @staticmethod
    def is_quiet_now(
        now_utc: datetime,
        timezone_offset_seconds: int,
        quiet_start: str | None,
        quiet_end: str | None,
    ) -> bool:
        if not quiet_start or not quiet_end:
            return False

        try:
            start_time = _parse_hhmm(quiet_start)
            end_time = _parse_hhmm(quiet_end)
        except ValueError:
            return False

        local_now = now_utc + timedelta(seconds=timezone_offset_seconds)
        local_time = local_now.time()

        if start_time < end_time:
            return start_time <= local_time < end_time
        # Overnight quiet range, e.g. 22:00-07:00.
        return local_time >= start_time or local_time < end_time

    def evaluate_events(
        self,
        forecast: NormalizedForecast,
        prefs: UserAlertPrefs,
        *,
        now_utc: datetime | None = None,
        hours: int,
        severe_only: bool,
    ) -> list[AlertEvent]:
        if not forecast.points:
            return []

        now = now_utc or datetime.now(timezone.utc)
        end = now + timedelta(hours=hours)

        collected: dict[str, AlertEvent] = {}

        for point in forecast.points:
            if point.dt_utc < now or point.dt_utc > end:
                continue

            for event in self._events_for_point(point, prefs):
                if severe_only and event.severity != "severe":
                    continue
                if event.event_type not in collected:
                    collected[event.event_type] = event

        return sorted(collected.values(), key=lambda item: item.starts_at_utc)

    def render_briefing_message(
        self,
        events: Iterable[AlertEvent],
        *,
        city_name: str,
        period_hours: int,
    ) -> str:
        events = list(events)
        if not events:
            return (
                f"<b>Briefing meteo ({city_name})</b>\n"
                f"Urmatoarele {period_hours}h: fara riscuri meteo relevante."
            )

        lines = [
            f"<b>Briefing meteo ({city_name})</b>",
            f"Riscuri estimate in urmatoarele {period_hours}h:",
        ]
        for event in events:
            icon = "🚨" if event.severity == "severe" else "⚠️"
            start_label = event.starts_at_utc.strftime("%d.%m %H:%M")
            lines.append(f"{icon} <b>{event.title}</b> de la {start_label}: {event.message}")

        return "\n".join(lines)

    def render_severe_message(self, event: AlertEvent, city_name: str) -> str:
        start_label = event.starts_at_utc.strftime("%d.%m %H:%M")
        return (
            f"🚨 <b>Alerta severa ({city_name})</b>\n"
            f"<b>{event.title}</b> de la {start_label}\n"
            f"{event.message}"
        )

    def _events_for_point(self, point: WeatherPoint, prefs: UserAlertPrefs) -> list[AlertEvent]:
        events: list[AlertEvent] = []

        if point.rain_mm_3h >= prefs.rain_mm_3h_threshold:
            severity = "severe" if point.rain_mm_3h >= self._severe_rain_threshold(prefs) else "normal"
            events.append(
                self._build_event(
                    point=point,
                    event_type="rain",
                    severity=severity,
                    title="Ploaie",
                    message=(
                        f"Cantitate estimata: {point.rain_mm_3h:.1f} mm/3h. "
                        "Ia umbrela si geaca impermeabila."
                    ),
                )
            )

        if point.snow_mm_3h >= prefs.snow_mm_3h_threshold:
            severity = "severe" if point.snow_mm_3h >= self._severe_snow_threshold(prefs) else "normal"
            events.append(
                self._build_event(
                    point=point,
                    event_type="snow",
                    severity=severity,
                    title="Ninsoare",
                    message=(
                        f"Cantitate estimata: {point.snow_mm_3h:.1f} mm/3h. "
                        "Pregateste haine groase si atentie la carosabil."
                    ),
                )
            )

        if point.wind_ms >= prefs.wind_ms_threshold:
            severity = "severe" if point.wind_ms >= self._severe_wind_ms else "normal"
            events.append(
                self._build_event(
                    point=point,
                    event_type="wind",
                    severity=severity,
                    title="Vant puternic",
                    message=f"Viteza estimata: {point.wind_ms:.1f} m/s.",
                )
            )

        if point.temp_c <= prefs.min_temp_c_threshold:
            severity = "severe" if point.temp_c <= self._severe_min_temp_c else "normal"
            events.append(
                self._build_event(
                    point=point,
                    event_type="cold",
                    severity=severity,
                    title="Temperatura scazuta",
                    message=f"Temperatura estimata: {point.temp_c:.1f}C.",
                )
            )

        if point.temp_c >= prefs.max_temp_c_threshold:
            severity = "severe" if point.temp_c >= self._severe_max_temp_c else "normal"
            events.append(
                self._build_event(
                    point=point,
                    event_type="heat",
                    severity=severity,
                    title="Temperatura ridicata",
                    message=f"Temperatura estimata: {point.temp_c:.1f}C.",
                )
            )

        return events

    def _severe_rain_threshold(self, prefs: UserAlertPrefs) -> float:
        return max(12.0, prefs.rain_mm_3h_threshold * 2.5)

    def _severe_snow_threshold(self, prefs: UserAlertPrefs) -> float:
        return max(8.0, prefs.snow_mm_3h_threshold * 2.5)

    @staticmethod
    def _build_event(
        *,
        point: WeatherPoint,
        event_type: str,
        severity: str,
        title: str,
        message: str,
    ) -> AlertEvent:
        key = f"{event_type}:{point.dt_utc.strftime('%Y%m%d%H')}:{severity}"
        return AlertEvent(
            event_key=key,
            event_type=event_type,
            severity=severity,
            starts_at_utc=point.dt_utc,
            title=title,
            message=message,
        )


def _parse_hhmm(raw: str) -> time:
    parts = raw.split(":")
    if len(parts) != 2:
        raise ValueError("invalid time")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("invalid time")
    return time(hour=hour, minute=minute)
