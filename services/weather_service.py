from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import aiohttp

from services.models import NormalizedForecast, WeatherPoint


LOGGER = logging.getLogger(__name__)


class WeatherProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class WeatherProvider(ABC):
    name: str

    @abstractmethod
    async def fetch(
        self,
        lat: float,
        lon: float,
        session: aiohttp.ClientSession,
        timeout: aiohttp.ClientTimeout,
    ) -> NormalizedForecast:
        raise NotImplementedError


class OpenWeatherProvider(WeatherProvider):
    name = "openweather"

    def __init__(self, api_key: str):
        self._api_key = api_key

    async def fetch(
        self,
        lat: float,
        lon: float,
        session: aiohttp.ClientSession,
        timeout: aiohttp.ClientTimeout,
    ) -> NormalizedForecast:
        if not self._api_key:
            raise WeatherProviderError(
                "WEATHER_API_KEY lipseste",
                retryable=False,
                status_code=401,
            )

        url = "https://api.openweathermap.org/data/2.5/forecast"
        params = {
            "lat": lat,
            "lon": lon,
            "appid": self._api_key,
            "units": "metric",
            "lang": "ro",
        }

        try:
            async with session.get(url, params=params, timeout=timeout) as response:
                if response.status == 401:
                    raise WeatherProviderError(
                        "OpenWeather unauthorized",
                        retryable=False,
                        status_code=401,
                    )
                if response.status >= 500:
                    raise WeatherProviderError(
                        f"OpenWeather server error: {response.status}",
                        retryable=True,
                        status_code=response.status,
                    )
                if response.status >= 400:
                    raise WeatherProviderError(
                        f"OpenWeather request failed: {response.status}",
                        retryable=False,
                        status_code=response.status,
                    )
                payload = await response.json()
        except aiohttp.ClientError as exc:
            raise WeatherProviderError(
                f"OpenWeather network error: {exc}",
                retryable=True,
            ) from exc

        return _normalize_openweather(payload)


class OpenMeteoProvider(WeatherProvider):
    name = "open-meteo"

    async def fetch(
        self,
        lat: float,
        lon: float,
        session: aiohttp.ClientSession,
        timeout: aiohttp.ClientTimeout,
    ) -> NormalizedForecast:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "timezone": "UTC",
            "hourly": "temperature_2m,apparent_temperature,relativehumidity_2m,windspeed_10m,precipitation,snowfall,weathercode",
            "daily": "sunrise,sunset",
            "forecast_days": 5,
        }

        try:
            async with session.get(url, params=params, timeout=timeout) as response:
                if response.status >= 500:
                    raise WeatherProviderError(
                        f"Open-Meteo server error: {response.status}",
                        retryable=True,
                        status_code=response.status,
                    )
                if response.status >= 400:
                    raise WeatherProviderError(
                        f"Open-Meteo request failed: {response.status}",
                        retryable=False,
                        status_code=response.status,
                    )
                payload = await response.json()
        except aiohttp.ClientError as exc:
            raise WeatherProviderError(
                f"Open-Meteo network error: {exc}",
                retryable=True,
            ) from exc

        return _normalize_openmeteo(payload)


class WeatherService:
    def __init__(
        self,
        providers: list[WeatherProvider],
        *,
        cache_ttl_seconds: int,
        retries: int,
        backoff_seconds: float,
        timeout_seconds: float,
        connect_timeout_seconds: float,
    ):
        self._providers = providers
        self._cache_ttl_seconds = cache_ttl_seconds
        self._retries = max(1, retries)
        self._backoff_seconds = max(0.0, backoff_seconds)
        self._timeout_seconds = timeout_seconds
        self._connect_timeout_seconds = connect_timeout_seconds
        self._cache: dict[tuple[float, float], tuple[float, NormalizedForecast]] = {}

    def _cache_key(self, lat: float, lon: float) -> tuple[float, float]:
        return (round(lat, 4), round(lon, 4))

    def _get_cached(self, lat: float, lon: float) -> NormalizedForecast | None:
        key = self._cache_key(lat, lon)
        entry = self._cache.get(key)
        if not entry:
            return None

        expires_monotonic, forecast = entry
        if time.monotonic() > expires_monotonic:
            self._cache.pop(key, None)
            return None
        return forecast

    def get_cached_provider(self, lat: float, lon: float) -> str | None:
        cached = self._get_cached(lat, lon)
        return cached.provider_name if cached else None

    async def get_forecast(
        self,
        lat: float,
        lon: float,
        session: aiohttp.ClientSession,
    ) -> NormalizedForecast | None:
        cached = self._get_cached(lat, lon)
        if cached:
            LOGGER.info(
                "forecast_fetch_ok",
                extra={
                    "metric": "forecast_fetch_ok",
                    "provider": cached.provider_name,
                    "cache": "hit",
                },
            )
            return cached

        timeout = aiohttp.ClientTimeout(
            total=self._timeout_seconds,
            connect=self._connect_timeout_seconds,
        )

        for provider in self._providers:
            for attempt in range(1, self._retries + 1):
                try:
                    forecast = await provider.fetch(lat, lon, session, timeout)
                    key = self._cache_key(lat, lon)
                    self._cache[key] = (
                        time.monotonic() + self._cache_ttl_seconds,
                        forecast,
                    )
                    LOGGER.info(
                        "forecast_fetch_ok",
                        extra={
                            "metric": "forecast_fetch_ok",
                            "provider": provider.name,
                            "cache": "miss",
                            "attempt": attempt,
                        },
                    )
                    return forecast
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    should_retry = attempt < self._retries
                    LOGGER.warning(
                        "forecast_fetch_fail",
                        extra={
                            "metric": "forecast_fetch_fail",
                            "provider": provider.name,
                            "attempt": attempt,
                            "retry": should_retry,
                            "error": str(exc),
                        },
                    )
                    if should_retry:
                        await asyncio.sleep(self._backoff_seconds * attempt)
                        continue
                    break
                except WeatherProviderError as exc:
                    should_retry = exc.retryable and attempt < self._retries
                    LOGGER.warning(
                        "forecast_fetch_fail",
                        extra={
                            "metric": "forecast_fetch_fail",
                            "provider": provider.name,
                            "attempt": attempt,
                            "retry": should_retry,
                            "status_code": exc.status_code,
                            "error": str(exc),
                        },
                    )
                    if should_retry:
                        await asyncio.sleep(self._backoff_seconds * attempt)
                        continue
                    break

        return None


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_openweather(payload: dict) -> NormalizedForecast:
    city = payload.get("city", {})
    city_name = city.get("name") or "Locatia ta"
    timezone_offset = _safe_int(city.get("timezone"), 0)

    sunrise_raw = city.get("sunrise")
    sunrise_utc = (
        datetime.fromtimestamp(int(sunrise_raw), tz=timezone.utc)
        if sunrise_raw is not None
        else None
    )
    sunset_raw = city.get("sunset")
    sunset_utc = (
        datetime.fromtimestamp(int(sunset_raw), tz=timezone.utc)
        if sunset_raw is not None
        else None
    )

    points: list[WeatherPoint] = []
    for item in payload.get("list", []):
        weather = (item.get("weather") or [{}])[0]
        dt_raw = item.get("dt")
        if dt_raw is None:
            continue
        points.append(
            WeatherPoint(
                dt_utc=datetime.fromtimestamp(int(dt_raw), tz=timezone.utc),
                temp_c=_safe_float(item.get("main", {}).get("temp")),
                feels_like_c=_safe_float(item.get("main", {}).get("feels_like")),
                condition_main=str(weather.get("main") or "Clouds"),
                description=str(weather.get("description") or "fara descriere"),
                humidity_percent=_safe_float(item.get("main", {}).get("humidity")),
                wind_ms=_safe_float(item.get("wind", {}).get("speed")),
                rain_mm_3h=_safe_float(item.get("rain", {}).get("3h"), 0.0),
                snow_mm_3h=_safe_float(item.get("snow", {}).get("3h"), 0.0),
            )
        )

    return NormalizedForecast(
        city_name=city_name,
        timezone_offset_seconds=timezone_offset,
        sunrise_utc=sunrise_utc,
        sunset_utc=sunset_utc,
        points=points,
        provider_name="openweather",
        fetched_at_utc=datetime.now(timezone.utc),
    )


OPEN_METEO_CODE_MAP: dict[int, tuple[str, str]] = {
    0: ("Clear", "senin"),
    1: ("Clouds", "mai mult senin"),
    2: ("Clouds", "partial innorat"),
    3: ("Clouds", "innorat"),
    45: ("Mist", "ceata"),
    48: ("Mist", "chiciura"),
    51: ("Drizzle", "burnita slaba"),
    53: ("Drizzle", "burnita"),
    55: ("Drizzle", "burnita intensa"),
    56: ("Freezing", "burnita inghetata slaba"),
    57: ("Freezing", "burnita inghetata intensa"),
    61: ("Rain", "ploaie slaba"),
    63: ("Rain", "ploaie"),
    65: ("Rain", "ploaie puternica"),
    66: ("Freezing", "ploaie inghetata slaba"),
    67: ("Freezing", "ploaie inghetata"),
    71: ("Snow", "ninsoare slaba"),
    73: ("Snow", "ninsoare"),
    75: ("Snow", "ninsoare abundenta"),
    77: ("Snow", "graupel"),
    80: ("Rain", "averse slabe"),
    81: ("Rain", "averse"),
    82: ("Rain", "averse puternice"),
    85: ("Snow", "averse de ninsoare slabe"),
    86: ("Snow", "averse de ninsoare puternice"),
    95: ("Thunderstorm", "furtuna"),
    96: ("Thunderstorm", "furtuna cu grindina"),
    99: ("Thunderstorm", "furtuna severa cu grindina"),
}


def _normalize_openmeteo(payload: dict) -> NormalizedForecast:
    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    temperatures = hourly.get("temperature_2m", [])
    apparent = hourly.get("apparent_temperature", [])
    humidity = hourly.get("relativehumidity_2m", [])
    wind = hourly.get("windspeed_10m", [])
    precipitation = hourly.get("precipitation", [])
    snowfall = hourly.get("snowfall", [])
    weathercodes = hourly.get("weathercode", [])

    points: list[WeatherPoint] = []
    for idx, raw_time in enumerate(times[:120]):
        if idx % 3 != 0:
            continue
        try:
            dt_utc = datetime.fromisoformat(str(raw_time)).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        code = _safe_int(weathercodes[idx] if idx < len(weathercodes) else 3, 3)
        condition_main, description = OPEN_METEO_CODE_MAP.get(code, ("Clouds", "innorat"))

        points.append(
            WeatherPoint(
                dt_utc=dt_utc,
                temp_c=_safe_float(temperatures[idx] if idx < len(temperatures) else None),
                feels_like_c=_safe_float(apparent[idx] if idx < len(apparent) else None),
                condition_main=condition_main,
                description=description,
                humidity_percent=_safe_float(humidity[idx] if idx < len(humidity) else None),
                wind_ms=_safe_float(wind[idx] if idx < len(wind) else None) / 3.6,
                rain_mm_3h=_safe_float(precipitation[idx] if idx < len(precipitation) else None),
                snow_mm_3h=_safe_float(snowfall[idx] if idx < len(snowfall) else None),
            )
        )

    daily = payload.get("daily", {})
    sunrise_vals = daily.get("sunrise", [])
    sunset_vals = daily.get("sunset", [])

    sunrise_utc = None
    sunset_utc = None
    if sunrise_vals:
        try:
            sunrise_utc = datetime.fromisoformat(str(sunrise_vals[0])).replace(tzinfo=timezone.utc)
        except ValueError:
            sunrise_utc = None
    if sunset_vals:
        try:
            sunset_utc = datetime.fromisoformat(str(sunset_vals[0])).replace(tzinfo=timezone.utc)
        except ValueError:
            sunset_utc = None

    timezone_offset = _safe_int(payload.get("utc_offset_seconds"), 0)

    return NormalizedForecast(
        city_name="Locatia ta",
        timezone_offset_seconds=timezone_offset,
        sunrise_utc=sunrise_utc,
        sunset_utc=sunset_utc,
        points=points,
        provider_name="open-meteo",
        fetched_at_utc=datetime.now(timezone.utc),
    )
