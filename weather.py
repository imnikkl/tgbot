from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from services.models import NormalizedForecast, WeatherPoint


def get_weather_emoji(condition: str) -> str:
    value = condition.lower()
    if "thunder" in value:
        return "🌩️"
    if "drizzle" in value:
        return "🌦️"
    if "rain" in value:
        return "🌧️"
    if "snow" in value:
        return "❄️"
    if "clear" in value:
        return "☀️"
    if "cloud" in value:
        return "☁️"
    if "mist" in value or "fog" in value:
        return "🌫️"
    return "🌤️"


def get_clothing_advice(condition: str, temp_c: float) -> str:
    condition_lower = condition.lower()
    advice: list[str] = []

    if "rain" in condition_lower or "drizzle" in condition_lower:
        advice.append("Ia umbrela si geaca impermeabila.")
    elif "snow" in condition_lower:
        advice.append("Poarta haine groase, caciula si manusi.")

    if temp_c <= 0:
        advice.append("Atentie la polei si suprafete alunecoase.")
    elif temp_c <= 10:
        advice.append("Poarta o geaca calduroasa.")
    elif temp_c >= 30:
        advice.append("Hidrateaza-te si evita expunerea lunga la soare.")
    else:
        advice.append("Imbraca-te confortabil pentru exterior.")

    return " ".join(advice)


def _local_dt(dt_utc: datetime, offset_seconds: int) -> datetime:
    return dt_utc + timedelta(seconds=offset_seconds)


def _sun_label(dt_utc: datetime | None, offset_seconds: int) -> str:
    if dt_utc is None:
        return "--:--"
    return _local_dt(dt_utc, offset_seconds).strftime("%H:%M")


def format_current_weather(forecast: NormalizedForecast) -> str:
    if not forecast.points:
        return "Nu am putut prelua date despre vreme in acest moment."

    point = forecast.points[0]
    local_dt = _local_dt(point.dt_utc, forecast.timezone_offset_seconds)

    report = (
        f"{get_weather_emoji(point.condition_main)} <b>Vremea în {forecast.city_name}</b>\n"
        f"<i>Actualizat: {local_dt.strftime('%d.%m %H:%M')}</i>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Condiții:</b> {point.description.capitalize()}\n"
        f"<b>Temperatură:</b> {round(point.temp_c)}°C <i>(se simte ca {round(point.feels_like_c)}°C)</i>\n"
        f"<b>Umiditate:</b> {round(point.humidity_percent)}%\n"
        f"<b>Vânt:</b> {point.wind_ms:.1f} m/s\n"
        f"<b>Ploaie 3h:</b> {point.rain_mm_3h:.1f} mm\n"
        f"<b>Ninsoare 3h:</b> {point.snow_mm_3h:.1f} mm\n\n"
        f"🌅 <b>Răsărit:</b> {_sun_label(forecast.sunrise_utc, forecast.timezone_offset_seconds)}"
        f" | 🌇 <b>Apus:</b> {_sun_label(forecast.sunset_utc, forecast.timezone_offset_seconds)}\n\n"
        f"<blockquote expand=\"True\">💡 <b>Sfat:</b> {get_clothing_advice(point.condition_main, point.temp_c)}</blockquote>"
    )
    return report


def _tomorrow_date(offset_seconds: int) -> datetime.date:
    local_now = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    return (local_now + timedelta(days=1)).date()


def format_tomorrow_weather(forecast: NormalizedForecast) -> str:
    if not forecast.points:
        return "Nu am putut prelua date despre vreme in acest moment."

    target_date = _tomorrow_date(forecast.timezone_offset_seconds)

    tomorrow_points = [
        point
        for point in forecast.points
        if _local_dt(point.dt_utc, forecast.timezone_offset_seconds).date() == target_date
    ]

    if not tomorrow_points:
        return "Nu s-au gasit date pentru ziua de maine in prognoza."

    noon_target = min(
        tomorrow_points,
        key=lambda point: abs(_local_dt(point.dt_utc, forecast.timezone_offset_seconds).hour - 12),
    )

    local_noon = _local_dt(noon_target.dt_utc, forecast.timezone_offset_seconds)

    return (
        f"📅 <b>Prognoza de mâine ({local_noon.strftime('%d.%m')})</b>\n"
        f"📍 <b>{forecast.city_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{get_weather_emoji(noon_target.condition_main)} <b>Condiții:</b> {noon_target.description.capitalize()}\n"
        f"🌡️ <b>Temperatură (aprox. la prânz):</b> {round(noon_target.temp_c)}°C "
        f"<i>(se simte ca {round(noon_target.feels_like_c)}°C)</i>\n"
        f"💧 <b>Umiditate:</b> {round(noon_target.humidity_percent)}%\n"
        f"🌬️ <b>Vânt:</b> {noon_target.wind_ms:.1f} m/s\n\n"
        f"<blockquote expand=\"True\">💡 <b>Sfat:</b> {get_clothing_advice(noon_target.condition_main, noon_target.temp_c)}</blockquote>"
    )


def format_3days_weather(forecast: NormalizedForecast) -> str:
    if not forecast.points:
        return "Nu am putut prelua date despre vreme in acest moment."

    local_today = (datetime.now(timezone.utc) + timedelta(seconds=forecast.timezone_offset_seconds)).date()
    daily: dict[str, dict[str, object]] = {}

    for point in forecast.points:
        local_dt = _local_dt(point.dt_utc, forecast.timezone_offset_seconds)
        date_value = local_dt.date()
        if date_value <= local_today:
            continue
        date_key = date_value.isoformat()

        day_bucket = daily.setdefault(
            date_key,
            {
                "date_display": local_dt.strftime("%d.%m"),
                "temps": [],
                "conditions": [],
            },
        )
        day_bucket["temps"].append(point.temp_c)
        day_bucket["conditions"].append(point.condition_main)

    if not daily:
        return "Nu exista suficiente date pentru urmatoarele 3 zile."

    days_ro = ["Luni", "Marți", "Miercuri", "Joi", "Vineri", "Sâmbătă", "Duminică"]
    lines = [f"🗓️ <b>Prognoza pe 3 zile în {forecast.city_name}</b>", "━━━━━━━━━━━━━━━━━━", ""]

    selected_dates = sorted(daily.keys())[:3]
    for date_key in selected_dates:
        payload = daily[date_key]
        dt_obj = datetime.strptime(date_key, "%Y-%m-%d")
        day_name = days_ro[dt_obj.weekday()]

        temps = payload["temps"]
        conditions = payload["conditions"]

        min_temp = round(min(temps))
        max_temp = round(max(temps))
        condition = Counter(conditions).most_common(1)[0][0]
        emoji = get_weather_emoji(condition)

        lines.append(f"<b>{day_name} ({payload['date_display']})</b> {emoji}")
        lines.append(f"🌡️ {min_temp}°C - {max_temp}°C")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)
