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
    temp = current["main"]["temp"]
    feels_like = current["main"]["feels_like"]
    description = current["weather"][0]["description"].capitalize()
    humidity = current["main"]["humidity"]
    wind_speed = current["wind"]["speed"]
    city_name = data.get("city", {}).get("name", "Locația ta")

    report = (
        f"🌡️ **Vremea în {city_name}**\n\n"
        f"**Condiții:** {description}\n"
        f"**Temperatura:** {temp}°C (se simte ca {feels_like}°C)\n"
        f"**Umiditate:** {humidity}%\n"
        f"**Vânt:** {wind_speed} m/s\n\n"
        f"💡 **Sfat:** {get_clothing_advice(current['weather'][0]['main'], temp)}"
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

    temp = target_item["main"]["temp"]
    feels_like = target_item["main"]["feels_like"]
    description = target_item["weather"][0]["description"].capitalize()
    humidity = target_item["main"]["humidity"]
    wind_speed = target_item["wind"]["speed"]
    city_name = data.get("city", {}).get("name", "Locația ta")

    report = (
        f"📅 **Vremea mâine în {city_name}**\n\n"
        f"**Condiții:** {description}\n"
        f"**Temperatura (la prânz):** {temp}°C (se simte ca {feels_like}°C)\n"
        f"**Umiditate:** {humidity}%\n"
        f"**Vânt:** {wind_speed} m/s\n\n"
        f"💡 **Sfat:** {get_clothing_advice(target_item['weather'][0]['main'], temp)}"
    )
    return report

