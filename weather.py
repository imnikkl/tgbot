import aiohttp
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

async def get_forecast(lat: float, lon: float) -> dict | None:
    """
    Fetches the 5-day / 3-hour forecast data from OpenWeatherMap.
    """
    if not WEATHER_API_KEY:
        print("Missing WEATHER_API_KEY")
        return None

    # Note: openweathermap /forecast endpoint doesn't return sunrise/sunset. 
    # To get sunrise/sunset we technically need the /weather endpoint too, 
    # but we can try to extract from city data if available, or just omit if not.
    # The /forecast endpoint DOES return city.sunrise and city.sunset!
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ro"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, ssl=False) as response:
            if response.status == 200:
                return await response.json()
            elif response.status == 401:
                return {"error": "unauthorized"}
            else:
                print(f"Error fetching weather: {response.status} - {await response.text()}")
                return None

def get_weather_emoji(condition: str) -> str:
    """Returns a large emoji based on the main weather condition."""
    condition = condition.lower()
    if "thunderstorm" in condition: return "🌩️"
    if "drizzle" in condition: return "🌦️"
    if "rain" in condition: return "🌧️"
    if "snow" in condition: return "❄️"
    if "clear" in condition: return "☀️"
    if "clouds" in condition or "cloud" in condition: return "☁️"
    return "🌤️"

def get_clothing_advice(condition: str, temp: float) -> str:
    condition = condition.lower()
    advice = []
    
    if "rain" in condition or "drizzle" in condition or "thunderstorm" in condition:
        advice.append("Ia-ți o umbrelă și o geacă impermeabilă!")
    elif "snow" in condition:
        advice.append("Pune-ți neapărat un fes, fular, mănuși și haine foarte groase!")
    elif "clear" in condition:
        if temp > 25:
            advice.append("Este însorit! Nu uita de ochelarii de soare și să bei multă apă.")
        elif temp < 10:
            advice.append("Este senin, dar răcoros. O geacă mai groasă este potrivită.")
        else:
            advice.append("Vreme plăcută, îmbracă-te confortabil.")
    elif "cloud" in condition:
        if temp < 10:
            advice.append("Este înnorat și frig. Îmbracă-te mai gros.")
        else:
            advice.append("Vreme înnorată. O jachetă ușoară ar putea fi de folos.")
             
    if temp <= 0 and "snow" not in condition:
        advice.append("Afară este îngheț! Pentru siguranță, îmbracă-te gros și ai grijă la polei.")
    elif 0 < temp <= 10 and not any("gros" in a or "groase" in a for a in advice):
        advice.append("Este destul de frig afară, pune-ți o haină călduroasă.")
    elif temp >= 30:
        advice.append("Este foarte cald! Îmbracă-te subțire și evită expunerea directă la soare.")

    if not advice:
         advice.append("Îmbracă-te potrivit pentru temperatura de afară.")
         
    return " ".join(advice)


async def analyze_forecast(data: dict) -> list[str]:
    """
    Analyzes the forecast data for the next ~2.5 days (20 periods of 3 hours)
    and returns a list of warnings if bad weather is detected.
    """
    if not data or "list" not in data:
        return []

    warnings = []
    # We look ahead roughly 2-3 days (40 is the max for 5 days, 20 is ~2.5 days)
    forecast_list = data["list"][:20]

    conditions_found = set()

    for item in forecast_list:
        temp = item["main"]["temp"]
        weather_main = item["weather"][0]["main"].lower() # e.g., 'rain', 'snow', etc.
        dt_txt = item["dt_txt"] # like 2026-02-26 12:00:00

        # Extract date for better message formatting
        date_obj = datetime.strptime(dt_txt, "%Y-%m-%d %H:%M:%S")
        date_str = date_obj.strftime("%d.%m %H:%M")

        # Check for bad weather
        if "rain" in weather_main and "rain" not in conditions_found:
            advice = get_clothing_advice(weather_main, temp)
            warnings.append(f"🌧️ Sunt așteptate ploi începând cu `{date_str}`. Temperatura: {temp}°C.\n💡 **Sfat:** {advice}")
            conditions_found.add("rain")
        
        if "snow" in weather_main and "snow" not in conditions_found:
            advice = get_clothing_advice(weather_main, temp)
            warnings.append(f"❄️ Sunt așteptate ninsori începând cu `{date_str}`. Temperatura: {temp}°C.\n💡 **Sfat:** {advice}")
            conditions_found.add("snow")

        # Freezing conditions
        if temp < 0 and "freezing" not in conditions_found:
            advice = get_clothing_advice("clear", temp) # condition doesn't matter much for freezing template
            warnings.append(f"🧊 Atenție la îngheț / polei! Temperaturi sub 0°C așteptate începând cu `{date_str}`.\n💡 **Sfat:** {advice}")
            conditions_found.add("freezing")

    return warnings

async def format_current_weather(data: dict) -> str:
    """
    Extracts the earliest forecast item to represent the current weather.
    """
    if not data or "list" not in data or len(data["list"]) == 0:
         return "Nu am putut prelua date despre vreme în acest moment."

    current = data["list"][0]
    temp = round(current["main"]["temp"])
    feels_like = round(current["main"]["feels_like"])
    condition_main = current["weather"][0]["main"]
    description = current["weather"][0]["description"].capitalize()
    humidity = current["main"]["humidity"]
    wind_speed = current["wind"]["speed"]
    city_name = data.get("city", {}).get("name", "Locația ta")
    
    # Extract sunrise and sunset if available
    sunrise_ts = data.get("city", {}).get("sunrise")
    sunset_ts = data.get("city", {}).get("sunset")
    sunrise_str = datetime.fromtimestamp(sunrise_ts).strftime('%H:%M') if sunrise_ts else "--:--"
    sunset_str = datetime.fromtimestamp(sunset_ts).strftime('%H:%M') if sunset_ts else "--:--"

    emoji = get_weather_emoji(condition_main)

    report = (
        f"{emoji} <b>Vremea în {city_name}</b>\n"
        f"──────────────\n"
        f"<b>Condiții:</b> {description}\n"
        f"<b>Temperatură:</b> {temp}°C <i>(se simte ca {feels_like}°C)</i>\n"
        f"<b>Umiditate:</b> {humidity}% 💧\n"
        f"<b>Vânt:</b> {wind_speed} m/s 🌬️\n\n"
        f"🌅 <b>Răsărit:</b> {sunrise_str}  |  🌇 <b>Apus:</b> {sunset_str}\n\n"
        f"💡 <i>Sfat:</i> {get_clothing_advice(condition_main, temp)}\n"
        f"──────────────"
    )
    return report

async def format_tomorrow_weather(data: dict) -> str:
    """
    Extracts the forecast for tomorrow (around noon if available) and formats it.
    """
    if not data or "list" not in data or len(data["list"]) == 0:
         return "Nu am putut prelua date despre vreme în acest moment."

    from datetime import datetime, timedelta
    
    # Calculate tomorrow's date
    tomorrow_dt = datetime.now() + timedelta(days=1)
    tomorrow_date_str = tomorrow_dt.strftime("%Y-%m-%d")
    
    target_item = None
    
    # First priority: Tomorrow at 12:00
    target_dt_txt = f"{tomorrow_date_str} 12:00:00"
    for item in data["list"]:
        if item["dt_txt"] == target_dt_txt:
            target_item = item
            break
            
    # Second priority: Any time tomorrow
    if not target_item:
        for item in data["list"]:
            if item["dt_txt"].startswith(tomorrow_date_str):
                target_item = item
                break

    if not target_item:
        return "Nu s-au găsit date pentru ziua de mâine în prognoză."

    temp = round(target_item["main"]["temp"])
    feels_like = round(target_item["main"]["feels_like"])
    condition_main = target_item["weather"][0]["main"]
    description = target_item["weather"][0]["description"].capitalize()
    humidity = target_item["main"]["humidity"]
    wind_speed = target_item["wind"]["speed"]
    city_name = data.get("city", {}).get("name", "Locația ta")
    emoji = get_weather_emoji(condition_main)

    report = (
        f"📅 <b>Prognoza de Mâine ({tomorrow_dt.strftime('%d.%m')})</b>\n"
        f"📍 <b>{city_name}</b>\n"
        f"──────────────\n"
        f"{emoji} <b>Condiții:</b> {description}\n"
        f"🌡️ <b>Temperatură (La Prânz):</b> {temp}°C <i>(se simte ca {feels_like}°C)</i>\n"
        f"💧 <b>Umiditate:</b> {humidity}%\n"
        f"🌬️ <b>Vânt:</b> {wind_speed} m/s\n\n"
        f"💡 <i>Sfat:</i> {get_clothing_advice(condition_main, temp)}\n"
        f"──────────────"
    )
    return report

async def format_3days_weather(data: dict) -> str:
    """
    Extracts a summarized forecast for the next 3 days.
    """
    if not data or "list" not in data or len(data["list"]) == 0:
         return "Nu am putut prelua date despre vreme în acest moment."

    from datetime import datetime
    
    city_name = data.get("city", {}).get("name", "Locația ta")
    daily_summaries = {}

    for item in data["list"]:
        dt_txt = item["dt_txt"]
        date_obj = datetime.strptime(dt_txt, "%Y-%m-%d %H:%M:%S")
        date_str = date_obj.strftime("%Y-%m-%d")
        
        # Skip today
        if date_str == datetime.now().strftime("%Y-%m-%d"):
            continue

        temp = item["main"]["temp"]
        condition = item["weather"][0]["main"]
        
        if date_str not in daily_summaries:
            # Explicitly type this as a dict for pyright/pyre to understand
            daily_summaries[date_str] = {
                "temps": [temp],
                "conditions": [condition],
                "date_display": date_obj.strftime("%d.%m")
            }
        else:
            daily_summaries[date_str]["temps"].append(temp)
            daily_summaries[date_str]["conditions"].append(condition)

        # Stop after 3 future days
        if len(daily_summaries) > 3:
            daily_summaries.popitem() # Remove the 4th day that was just added
            break

    report = f"🗓️ <b>Prognoza pe 3 Zile în {city_name}</b>\n──────────────\n\n"

    days_ro = ["Luni", "Marți", "Miercuri", "Joi", "Vineri", "Sâmbătă", "Duminică"]

    for date_str, summary in daily_summaries.items():
        min_temp = round(min(summary["temps"]))
        max_temp = round(max(summary["temps"]))
        
        # Get the most common condition for the day to assign the emoji
        from collections import Counter
        most_common_condition = Counter(summary["conditions"]).most_common(1)[0][0]
        emoji = get_weather_emoji(most_common_condition)
        
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        day_name = days_ro[date_obj.weekday()]

        report += f"<b>{day_name} ({summary['date_display']})</b> {emoji}\n"
        report += f"🌡️ {min_temp}°C - {max_temp}°C\n\n"

    report += "──────────────"
    return report

