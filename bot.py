import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

import database
from weather import get_forecast, format_current_weather

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_location_keyboard() -> ReplyKeyboardMarkup:
    """Returns a keyboard with a button to request the user's location."""
    button = KeyboardButton(text="📍 Trimite Locația", request_location=True)
    keyboard = ReplyKeyboardMarkup(keyboard=[[button]], resize_keyboard=True, one_time_keyboard=True)
    return keyboard

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    """Handler for the /start command."""
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
            "Vei primi alerte automate dacă se anunță vreme rea în zilele următoare.\n\n"
            f"Iată starea vremii în acest moment:\n\n{weather_report}"
        )
    elif forecast_data and forecast_data.get("error") == "unauthorized":
        success_text = (
            "✅ Locația ta a fost salvată cu succes!\n\n"
            "⚠️ **Atenție:** Cheia ta API de la OpenWeatherMap este invalidă sau încă nu a fost activată. "
            "Dacă abia ai creat-o, durează de obicei între 1 și 2 ore să fie activată de serverele lor.\n"
            "Până atunci, botul nu poate prelua datele meteo."
        )
    else:
        success_text = (
            "✅ Locația ta a fost salvată cu succes!\n"
            "Din păcate, am întâmpinat o eroare la preluarea datelor meteo acum, "
            "dar te voi anunța imediat ce detectez vreme rea."
        )

    # Remove the reply keyboard
    await message.answer(success_text, reply_markup=types.ReplyKeyboardRemove())

@dp.message(Command("vreme"))
async def cmd_vreme(message: types.Message):
    """Handler for the /vreme command to get current weather on demand."""
    user_id = message.from_user.id
    user_data = await database.get_user(user_id)

    if not user_data:
        await message.answer(
            "Nu am locația ta salvată. Te rog folosește comanda /start pentru a-mi trimite locația."
        )
        return

    lat = user_data["latitude"]
    lon = user_data["longitude"]

    forecast_data = await get_forecast(lat, lon)
    if forecast_data:
        weather_report = await format_current_weather(forecast_data)
        await message.answer(weather_report)
    else:
        await message.answer("Îmi pare rău, nu am putut prelua datele meteo momentan.")

