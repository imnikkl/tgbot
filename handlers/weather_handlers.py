from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import aiohttp
from aiogram import F, Router, types
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, KeyboardButton, ReplyKeyboardMarkup

from repositories.user_repo import UserRepository
from services.alert_engine import AlertEngine
from services.weather_service import WeatherService
from services.ai_service import AiService
from weather import format_3days_weather, format_current_weather, format_tomorrow_weather


LOGGER = logging.getLogger(__name__)
router = Router()


_user_repo: UserRepository | None = None
_weather_service: WeatherService | None = None
_http_session: aiohttp.ClientSession | None = None
_alert_engine: AlertEngine | None = None
_ai_service: AiService | None = None
_morning_hour = 7
_morning_minute = 30
_evening_hour = 19
_evening_minute = 30


def configure_handlers(
    *,
    user_repo: UserRepository,
    weather_service: WeatherService,
    http_session: aiohttp.ClientSession,
    alert_engine: AlertEngine,
    ai_service: AiService,
    morning_hour: int = 7,
    morning_minute: int = 30,
    evening_hour: int = 19,
    evening_minute: int = 30,
) -> None:
    global _user_repo, _weather_service, _http_session, _alert_engine, _ai_service
    global _morning_hour, _morning_minute, _evening_hour, _evening_minute
    _user_repo = user_repo
    _weather_service = weather_service
    _http_session = http_session
    _alert_engine = alert_engine
    _ai_service = ai_service
    _morning_hour = morning_hour
    _morning_minute = morning_minute
    _evening_hour = evening_hour
    _evening_minute = evening_minute


def get_bot_commands() -> list[BotCommand]:
    return [
        BotCommand(command="start", description="Porneste botul"),
        BotCommand(command="help", description="Lista comenzi"),
        BotCommand(command="vreme", description="Vremea curenta"),
        BotCommand(command="maine", description="Prognoza pentru maine"),
        BotCommand(command="zile3", description="Prognoza pe 3 zile"),
        BotCommand(command="alerte", description="Praguri si setari alerte"),
        BotCommand(command="liniste", description="Seteaza ore de liniste"),
        BotCommand(command="status", description="Status configuratie"),
    ]


def get_location_keyboard() -> ReplyKeyboardMarkup:
    button = KeyboardButton(text="📍 Trimite Locatia", request_location=True)
    return ReplyKeyboardMarkup(
        keyboard=[[button]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌡️ Vremea Acum"), KeyboardButton(text="📅 Prognoza Maine")],
            [KeyboardButton(text="🗓️ Prognoza 3 Zile"), KeyboardButton(text="🔔 Setari Alerte")],
            [KeyboardButton(text="😴 Ore Liniste"), KeyboardButton(text="⚙️ Status")],
            [KeyboardButton(text="📍 Actualizeaza Locatia", request_location=True)],
        ],
        resize_keyboard=True,
    )


def _deps() -> tuple[UserRepository, WeatherService, aiohttp.ClientSession, AlertEngine]:
    if not _user_repo or not _weather_service or not _http_session or not _alert_engine:
        raise RuntimeError("Handler dependencies are not configured")
    return _user_repo, _weather_service, _http_session, _alert_engine


def parse_alert_update_args(args: str) -> tuple[dict, str | None]:
    args = args.strip()
    if not args:
        return {}, None

    updates: dict = {}
    mapping = {
        "ploaie": "rain_mm_3h_threshold",
        "ninsoare": "snow_mm_3h_threshold",
        "vant": "wind_ms_threshold",
        "min": "min_temp_c_threshold",
        "max": "max_temp_c_threshold",
        "cooldown": "alert_cooldown_minutes",
        "dimineata": "daily_morning_enabled",
        "seara": "daily_evening_enabled",
        "sever": "severe_immediate_enabled",
    }

    for chunk in args.split():
        if "=" not in chunk:
            return {}, f"Format invalid: {chunk}. Foloseste cheia=valoare."
        key, raw_value = chunk.split("=", 1)
        key = key.lower().strip()
        raw_value = raw_value.strip().lower()

        if key not in mapping:
            return {}, f"Cheie necunoscuta: {key}."

        mapped = mapping[key]
        if mapped in {
            "daily_morning_enabled",
            "daily_evening_enabled",
            "severe_immediate_enabled",
        }:
            parsed_bool = _parse_bool(raw_value)
            if parsed_bool is None:
                return {}, f"Valoare invalida pentru {key}: {raw_value}. Foloseste on/off."
            updates[mapped] = parsed_bool
            continue

        try:
            if mapped == "alert_cooldown_minutes":
                value = int(raw_value)
            else:
                value = float(raw_value)
        except ValueError:
            return {}, f"Valoare numerica invalida pentru {key}: {raw_value}."

        if mapped == "rain_mm_3h_threshold" and not (0 <= value <= 60):
            return {}, "ploaie trebuie sa fie intre 0 si 60 mm/3h."
        if mapped == "snow_mm_3h_threshold" and not (0 <= value <= 60):
            return {}, "ninsoare trebuie sa fie intre 0 si 60 mm/3h."
        if mapped == "wind_ms_threshold" and not (1 <= value <= 60):
            return {}, "vant trebuie sa fie intre 1 si 60 m/s."
        if mapped == "min_temp_c_threshold" and not (-60 <= value <= 20):
            return {}, "min trebuie sa fie intre -60 si 20 C."
        if mapped == "max_temp_c_threshold" and not (20 <= value <= 60):
            return {}, "max trebuie sa fie intre 20 si 60 C."
        if mapped == "alert_cooldown_minutes" and not (15 <= value <= 1440):
            return {}, "cooldown trebuie sa fie intre 15 si 1440 minute."

        updates[mapped] = value

    return updates, None


def parse_quiet_hours_arg(args: str) -> tuple[str | None, str | None]:
    value = args.strip().lower()
    if value in {"off", "dezactivat", "none"}:
        return None, None

    match = re.match(r"^([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)$", value)
    if not match:
        raise ValueError("Format invalid. Foloseste HH:MM-HH:MM sau /liniste off")

    start = f"{match.group(1)}:{match.group(2)}"
    end = f"{match.group(3)}:{match.group(4)}"
    if start == end:
        raise ValueError("Interval invalid: inceputul nu poate fi egal cu sfarsitul")

    return start, end


def _parse_bool(value: str) -> bool | None:
    if value in {"on", "da", "yes", "1", "true"}:
        return True
    if value in {"off", "nu", "no", "0", "false"}:
        return False
    return None


def _extract_command_args(message: types.Message) -> str:
    text = (message.text or "").strip()
    if " " not in text:
        return ""
    return text.split(" ", 1)[1].strip()


def _help_text() -> str:
    return (
        "<b>Comenzi disponibile</b>\n"
        "/start - initializare\n"
        "/vreme - vremea curenta\n"
        "/maine - prognoza maine\n"
        "/3zile sau /zile3 - prognoza pe 3 zile\n"
        "/alerte - vezi setari curente\n"
        "/alerte ploaie=3 vant=12 min=-2 max=34 cooldown=180\n"
        "/alerte dimineata=on seara=on sever=on\n"
        "/liniste 22:00-07:00 - seteaza ore de liniste\n"
        "/liniste off - dezactiveaza orele de liniste\n"
        "/status - status complet configuratie"
    )


def _format_alert_settings(user: dict) -> str:
    return (
        "<b>Setari alerte</b>\n"
        f"Ploaie: {float(user['rain_mm_3h_threshold']):.1f} mm/3h\n"
        f"Ninsoare: {float(user['snow_mm_3h_threshold']):.1f} mm/3h\n"
        f"Vant: {float(user['wind_ms_threshold']):.1f} m/s\n"
        f"Temp minima: {float(user['min_temp_c_threshold']):.1f}C\n"
        f"Temp maxima: {float(user['max_temp_c_threshold']):.1f}C\n"
        f"Cooldown: {int(user['alert_cooldown_minutes'])} minute\n"
        f"Briefing dimineata: {'ON' if int(user['daily_morning_enabled']) else 'OFF'}\n"
        f"Briefing seara: {'ON' if int(user['daily_evening_enabled']) else 'OFF'}\n"
        f"Sever imediat: {'ON' if int(user['severe_immediate_enabled']) else 'OFF'}"
    )


def _next_window_label(hour: int, minute: int, tz_name: str) -> str:
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)
    target = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now_local:
        target += timedelta(days=1)
    return target.strftime("%d.%m %H:%M")


async def _require_user(message: types.Message) -> dict | None:
    user_repo, _, _, _ = _deps()
    user = await user_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer(
            "Nu am locatia ta salvata. Trimite locatia din butonul de mai jos.",
            reply_markup=get_location_keyboard(),
        )
        return None
    return user


async def _send_typing(message: types.Message) -> None:
    try:
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    except Exception:
        pass


@router.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    user_repo, _, _, _ = _deps()
    existing = await user_repo.get_user(message.from_user.id)

    if existing:
        await message.answer(
            f"Salut din nou, {message.from_user.first_name}! Foloseste meniul de mai jos.",
            reply_markup=get_main_keyboard(),
        )
        return

    welcome = (
        f"Salut, {message.from_user.first_name}!\n\n"
        "Sunt asistentul tau meteo. Trimite locatia curenta ca sa pot porni alertele inteligente."
    )
    await message.answer(welcome, reply_markup=get_location_keyboard())


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    await message.answer(_help_text(), reply_markup=get_main_keyboard())


@router.message(F.content_type == types.ContentType.LOCATION)
async def on_location(message: types.Message) -> None:
    user_repo, weather_service, session, _ = _deps()

    lat = float(message.location.latitude)
    lon = float(message.location.longitude)

    await user_repo.upsert_user_location(
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        latitude=lat,
        longitude=lon,
    )

    await _send_typing(message)
    forecast = await weather_service.get_forecast(lat, lon, session)

    if forecast is None:
        await message.answer(
            "Locatia a fost salvata, dar nu am putut prelua meteo chiar acum.",
            reply_markup=get_main_keyboard(),
        )
        return

    await message.answer(
        "✅ Locatia ta a fost salvata cu succes.\n\n" + format_current_weather(forecast),
        reply_markup=get_main_keyboard(),
    )


@router.message(Command("vreme"))
@router.message(F.text == "🌡️ Vremea Acum")
async def cmd_vreme(message: types.Message) -> None:
    user = await _require_user(message)
    if user is None:
        return

    _, weather_service, session, _ = _deps()

    await _send_typing(message)
    forecast = await weather_service.get_forecast(user["latitude"], user["longitude"], session)
    if not forecast:
        await message.answer("Nu am putut prelua datele meteo momentan.", reply_markup=get_main_keyboard())
        return

    await message.answer(format_current_weather(forecast), reply_markup=get_main_keyboard())


@router.message(Command("maine"))
@router.message(F.text == "📅 Prognoza Maine")
async def cmd_maine(message: types.Message) -> None:
    user = await _require_user(message)
    if user is None:
        return

    _, weather_service, session, _ = _deps()

    await _send_typing(message)
    forecast = await weather_service.get_forecast(user["latitude"], user["longitude"], session)
    if not forecast:
        await message.answer("Nu am putut prelua datele meteo momentan.", reply_markup=get_main_keyboard())
        return

    await message.answer(format_tomorrow_weather(forecast), reply_markup=get_main_keyboard())


@router.message(Command("3zile"))
@router.message(Command("zile3"))
@router.message(F.text == "🗓️ Prognoza 3 Zile")
async def cmd_3zile(message: types.Message) -> None:
    user = await _require_user(message)
    if user is None:
        return

    _, weather_service, session, _ = _deps()

    await _send_typing(message)
    forecast = await weather_service.get_forecast(user["latitude"], user["longitude"], session)
    if not forecast:
        await message.answer("Nu am putut prelua datele meteo momentan.", reply_markup=get_main_keyboard())
        return

    await message.answer(format_3days_weather(forecast), reply_markup=get_main_keyboard())


@router.message(Command("alerte"))
@router.message(F.text == "🔔 Setari Alerte")
async def cmd_alerte(message: types.Message) -> None:
    user_repo, _, _, _ = _deps()

    user = await _require_user(message)
    if user is None:
        return

    args = _extract_command_args(message)
    if not args:
        await message.answer(
            _format_alert_settings(user)
            + "\n\nExemplu: /alerte ploaie=3 vant=12 min=-2 max=34 cooldown=180",
            reply_markup=get_main_keyboard(),
        )
        return

    updates, error = parse_alert_update_args(args)
    if error:
        await message.answer(error, reply_markup=get_main_keyboard())
        return

    await user_repo.update_alert_preferences(message.from_user.id, **updates)
    fresh_user = await user_repo.get_user(message.from_user.id)
    await message.answer(
        "✅ Setarile de alerta au fost actualizate.\n\n" + _format_alert_settings(fresh_user),
        reply_markup=get_main_keyboard(),
    )


@router.message(Command("liniste"))
@router.message(F.text == "😴 Ore Liniste")
async def cmd_liniste(message: types.Message) -> None:
    user_repo, _, _, _ = _deps()
    user = await _require_user(message)
    if user is None:
        return

    args = _extract_command_args(message)
    if not args:
        quiet_start = user.get("quiet_start")
        quiet_end = user.get("quiet_end")
        if quiet_start and quiet_end:
            text = f"Interval activ: {quiet_start}-{quiet_end}"
        else:
            text = "Orele de liniste sunt dezactivate."
        text += "\nExemplu: /liniste 22:00-07:00 sau /liniste off"
        await message.answer(text, reply_markup=get_main_keyboard())
        return

    try:
        start, end = parse_quiet_hours_arg(args)
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=get_main_keyboard())
        return

    await user_repo.update_quiet_hours(message.from_user.id, start, end)

    if start is None:
        await message.answer("✅ Orele de liniste au fost dezactivate.", reply_markup=get_main_keyboard())
        return

    await message.answer(
        f"✅ Orele de liniste au fost setate: {start}-{end}",
        reply_markup=get_main_keyboard(),
    )


@router.message(Command("status"))
@router.message(F.text == "⚙️ Status")
async def cmd_status(message: types.Message) -> None:
    user = await _require_user(message)
    if user is None:
        return

    _, weather_service, session, _ = _deps()

    forecast = await weather_service.get_forecast(user["latitude"], user["longitude"], session)
    provider = forecast.provider_name if forecast else weather_service.get_cached_provider(user["latitude"], user["longitude"])
    provider = provider or "necunoscut"

    quiet_start = user.get("quiet_start")
    quiet_end = user.get("quiet_end")
    quiet_label = f"{quiet_start}-{quiet_end}" if quiet_start and quiet_end else "dezactivate"

    tz_name = user.get("timezone") or "Europe/Bucharest"
    next_morning = _next_window_label(_morning_hour, _morning_minute, tz_name)
    next_evening = _next_window_label(_evening_hour, _evening_minute, tz_name)

    text = (
        "<b>Status cont</b>\n"
        f"Locatie activa: da ({user['latitude']:.4f}, {user['longitude']:.4f})\n"
        f"Provider meteo: {provider}\n"
        f"Ore liniste: {quiet_label}\n"
        f"Cooldown alerta: {int(user['alert_cooldown_minutes'])} minute\n"
        f"Prag ploaie: {float(user['rain_mm_3h_threshold']):.1f} mm/3h\n"
        f"Prag ninsoare: {float(user['snow_mm_3h_threshold']):.1f} mm/3h\n"
        f"Prag vant: {float(user['wind_ms_threshold']):.1f} m/s\n"
        f"Temp min/max: {float(user['min_temp_c_threshold']):.1f}C / {float(user['max_temp_c_threshold']):.1f}C\n"
        f"Briefing dimineata: {'ON' if int(user['daily_morning_enabled']) else 'OFF'} ({next_morning})\n"
        f"Briefing seara: {'ON' if int(user['daily_evening_enabled']) else 'OFF'} ({next_evening})\n"
        f"Sever imediat: {'ON' if int(user['severe_immediate_enabled']) else 'OFF'}"
    )

    await message.answer(text, reply_markup=get_main_keyboard())


@router.message()
async def fallback_handler(message: types.Message) -> None:
    user_repo, weather_service, session, _ = _deps()
    user = await user_repo.get_user(message.from_user.id)
    
    if not user or not _ai_service or not _ai_service.is_configured:
        await message.answer(
            "Nu am inteles comanda. Foloseste /help pentru instructiuni.",
            reply_markup=get_main_keyboard(),
        )
        return

    await _send_typing(message)
    
    forecast = await weather_service.get_forecast(user["latitude"], user["longitude"], session)
    if not forecast:
        await message.answer("Nu am putut prelua datele meteo momentan pentru a raspunde intrebarii.", reply_markup=get_main_keyboard())
        return

    weather_context = format_current_weather(forecast) + "\n\n" + format_tomorrow_weather(forecast)

    response = await _ai_service.get_intelligent_response(
        question=message.text or "",
        weather_context=weather_context
    )
    
    await message.answer(response, reply_markup=get_main_keyboard())
