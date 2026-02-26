import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import database
from weather import get_forecast, analyze_forecast
from bot import bot

async def check_weather_and_alert():
    """
    Checks the weather for all registered users and sends an alert if necessary.
    """
    print("Running scheduled weather check...")
    users = await database.get_all_users()
    
    for user in users:
        chat_id = user["chat_id"]
        lat = user["latitude"]
        lon = user["longitude"]

        forecast_data = await get_forecast(lat, lon)
        if not forecast_data:
            continue

        warnings = await analyze_forecast(forecast_data)
        
        if warnings:
            message_text = "⚠️ **Alertă Meteo** ⚠️\n\nS-au anunțat condiții meteo nefavorabile în zona ta în următoarele zile:\n\n"
            message_text += "\n\n".join(warnings)
            
            try:
                await bot.send_message(chat_id=chat_id, text=message_text, parse_mode="Markdown")
                print(f"Sent alert to {chat_id}")
            except Exception as e:
                print(f"Failed to send alert to {chat_id}: {e}")

        # Adding a small delay to avoid hitting rate limits
        await asyncio.sleep(1)

def setup_scheduler() -> AsyncIOScheduler:
    """Initializes and returns the scheduler."""
    scheduler = AsyncIOScheduler()
    
    # Run the check every day at 08:00 AM (server time).
    # You can change this to be more frequent if needed for testing (e.g. trigger='interval', minutes=1)
    scheduler.add_job(check_weather_and_alert, 'cron', hour=8, minute=0)
    
    return scheduler
