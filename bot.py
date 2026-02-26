from datetime import datetime
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

import database
from weather import get_forecast, format_current_weather, format_tomorrow_weather, format_3days_weather

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

def get_location_keyboard() -> ReplyKeyboardMarkup:
    """Returns a keyboard with a button to request the user's location initially."""
    button = KeyboardButton(text="📍 Trimite Locația", request_location=True)
    keyboard = ReplyKeyboardMarkup(keyboard=[[button]], resize_keyboard=True, one_time_keyboard=True)
    return keyboard

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Returns the main keyboard with action buttons."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌡️ Vremea Acum"), KeyboardButton(text="📅 Prognoza Mâine")],
            [KeyboardButton(text="🗓️ Prognoza pe 3 Zile")],
            [KeyboardButton(text="📍 Actualizează Locația", request_location=True)]
        ],
        resize_keyboard=True
    )
    return keyboard

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    """Handler for the /start command."""
    user_id = message.from_user.id
    user_data = await database.get_user(user_id)
    
    current_hour = datetime.now().hour
    if 5 <= current_hour < 12:
        greeting = "Bună dimineața"
    elif 12 <= current_hour < 18:
        greeting = "Bună ziua"
    else:
        greeting = "Bună seara"
        
    if user_data:
        welcome_text = f"<b>{greeting} din nou, {message.from_user.first_name}!</b> 👋\n\nFolosește meniul de mai jos pentru a afla vremea."
        await message.answer(welcome_text, reply_markup=get_main_keyboard())
    else:
        welcome_text = (
            f"<b>{greeting}, {message.from_user.first_name}!</b> 👋\n\n"
            "Sunt un asistent meteo inteligent care te va anunța în legătură cu starea vremii (ploi, ninsori, îngheț).\n"
            "Pentru a începe, am nevoie să știu unde te afli.\n\n"
            "👇 <b>Te rog apasă pe butonul de mai jos pentru a-mi trimite locația ta curentă.</b>"
        )
        await message.answer(welcome_text, reply_markup=get_location_keyboard())

@dp.message(F.content_type == types.ContentType.LOCATION)
async def handle_location(message: types.Message):
    """Handles location messages sent by the user."""
    lat = message.location.latitude
    lon = message.location.longitude
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Save to database
    await database.upsert_user(user_id, chat_id, lat, lon)

    # Fetch initial weather to confirm it works
    forecast_data = await get_forecast(lat, lon)
    if forecast_data and "error" not in forecast_data:
        weather_report = await format_current_weather(forecast_data)
        success_text = (
            "✅ <b>Locația ta a fost salvată cu succes!</b>\n\n"
            "Acum poți folosi meniul de mai jos oricând dorești să verifici cum este afară.\n\n"
            f"{weather_report}"
        )
    elif forecast_data and forecast_data.get("error") == "unauthorized":
        success_text = (
            "✅ <b>Locația ta a fost salvată cu succes!</b>\n\n"
            "⚠️ <b>Atenție:</b> Cheia API OpenWeatherMap este invalidă/neactivată.\n"
        )
    else:
        success_text = (
            "✅ <b>Locația ta a fost salvată cu succes!</b>\n"
            "Din păcate, am întâmpinat o eroare la preluarea datelor meteo acum."
        )

    # We send the permanent functional keyboard
    await message.answer(success_text, reply_markup=get_main_keyboard())

@dp.message(Command("vreme"))
@dp.message(F.text == "🌡️ Vremea Acum")
async def btn_vreme_acum(message: types.Message):
    """Handler for current weather."""
    user_id = message.from_user.id
    user_data = await database.get_user(user_id)

    if not user_data:
        await message.answer("Nu am locația ta salvată. Te rog apasă pe '📍 Actualizează Locația' sau folosește /start.", reply_markup=get_location_keyboard())
        return

    lat = user_data["latitude"]
    lon = user_data["longitude"]

    # Show a typing effect
    try:
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    except:
        pass

    forecast_data = await get_forecast(lat, lon)
    if forecast_data and "error" not in forecast_data:
        weather_report = await format_current_weather(forecast_data)
        await message.answer(weather_report, reply_markup=get_main_keyboard())
    else:
        await message.answer("Îmi pare rău, nu am putut prelua datele meteo momentan.", reply_markup=get_main_keyboard())

@dp.message(F.text == "📅 Prognoza Mâine")
async def btn_prognoza_maine(message: types.Message):
    """Handler for tomorrow's weather."""
    user_id = message.from_user.id
    user_data = await database.get_user(user_id)

    if not user_data:
        await message.answer("Nu am locația ta salvată. Te rog apasă pe '📍 Actualizează Locația' sau folosește /start.", reply_markup=get_location_keyboard())
        return

    lat = user_data["latitude"]
    lon = user_data["longitude"]

    try:
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    except:
        pass

    forecast_data = await get_forecast(lat, lon)
    if forecast_data and "error" not in forecast_data:
        weather_report = await format_tomorrow_weather(forecast_data)
        await message.answer(weather_report, reply_markup=get_main_keyboard())
    else:
        await message.answer("Îmi pare rău, nu am putut prelua datele meteo momentan.", reply_markup=get_main_keyboard())

@dp.message(F.text == "🗓️ Prognoza pe 3 Zile")
async def btn_prognoza_3_zile(message: types.Message):
    """Handler for the 3 days forecast."""
    user_id = message.from_user.id
    user_data = await database.get_user(user_id)

    if not user_data:
        await message.answer("Nu am locația ta salvată. Te rog apasă pe '📍 Actualizează Locația' sau folosește /start.", reply_markup=get_location_keyboard())
        return

    lat = user_data["latitude"]
    lon = user_data["longitude"]

    try:
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    except:
        pass

    forecast_data = await get_forecast(lat, lon)
    if forecast_data and "error" not in forecast_data:
        weather_report = await format_3days_weather(forecast_data)
        await message.answer(weather_report, reply_markup=get_main_keyboard())
    else:
        await message.answer("Îmi pare rău, nu am putut prelua datele meteo momentan.", reply_markup=get_main_keyboard())
