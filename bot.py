import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

import database
from weather import get_forecast, format_current_weather, format_tomorrow_weather

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
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
    
    if user_data:
        welcome_text = f"Salutare din nou, {message.from_user.first_name}!\n\nFolosește meniul de mai jos pentru a afla vremea."
        await message.answer(welcome_text, reply_markup=get_main_keyboard())
    else:
        welcome_text = (
            f"Salut, {message.from_user.first_name}!\n\n"
            "Sunt un bot care te va anunța în legătură cu starea vremii (ploi, ninsori, îngheț).\n"
            "Pentru a începe, am nevoie să știu unde te afli.\n\n"
            "Te rog apasă pe butonul de mai jos pentru a-mi trimite locația ta curentă."
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
            "✅ Locația ta a fost salvată cu succes!\n\n"
            "Acum poți folosi meniul de mai jos oricând dorești să verifici cum este afară.\n\n"
            "Iată starea vremii în acest moment:\n\n"
            f"{weather_report}"
        )
    elif forecast_data and forecast_data.get("error") == "unauthorized":
        success_text = (
            "✅ Locația ta a fost salvată cu succes!\n\n"
            "⚠️ **Atenție:** Cheia API OpenWeatherMap este invalidă/neactivată.\n"
        )
    else:
        success_text = (
            "✅ Locația ta a fost salvată cu succes!\n"
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
