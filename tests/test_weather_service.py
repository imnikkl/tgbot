from __future__ import annotations

import unittest
from datetime import datetime, timezone

import aiohttp

from services.models import NormalizedForecast, WeatherPoint
from services.weather_service import WeatherProvider, WeatherProviderError, WeatherService


class _FailingProvider(WeatherProvider):
    name = "primary"

    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, lat, lon, session, timeout):
        self.calls += 1
        raise WeatherProviderError("unauthorized", retryable=False, status_code=401)


class _FallbackProvider(WeatherProvider):
    name = "fallback"

    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, lat, lon, session, timeout):
        self.calls += 1
        point = WeatherPoint(
            dt_utc=datetime.now(timezone.utc),
            temp_c=20,
            feels_like_c=20,
            condition_main="Clear",
            description="senin",
            humidity_percent=50,
            wind_ms=2,
            rain_mm_3h=0,
            snow_mm_3h=0,
        )
        return NormalizedForecast(
            city_name="Test",
            timezone_offset_seconds=0,
            sunrise_utc=None,
            sunset_utc=None,
            points=[point],
            provider_name=self.name,
            fetched_at_utc=datetime.now(timezone.utc),
        )


class WeatherServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.session = aiohttp.ClientSession()

    async def asyncTearDown(self) -> None:
        await self.session.close()

    async def test_fallback_used_when_primary_fails(self) -> None:
        primary = _FailingProvider()
        fallback = _FallbackProvider()
        service = WeatherService(
            providers=[primary, fallback],
            cache_ttl_seconds=600,
            retries=1,
            backoff_seconds=0,
            timeout_seconds=5,
            connect_timeout_seconds=2,
        )

        forecast = await service.get_forecast(44.4, 26.1, self.session)

        self.assertIsNotNone(forecast)
        self.assertEqual(forecast.provider_name, "fallback")
        self.assertEqual(primary.calls, 1)
        self.assertEqual(fallback.calls, 1)

    async def test_cache_prevents_duplicate_fetch(self) -> None:
        fallback = _FallbackProvider()
        service = WeatherService(
            providers=[fallback],
            cache_ttl_seconds=600,
            retries=1,
            backoff_seconds=0,
            timeout_seconds=5,
            connect_timeout_seconds=2,
        )

        forecast_one = await service.get_forecast(44.4, 26.1, self.session)
        forecast_two = await service.get_forecast(44.4, 26.1, self.session)

        self.assertIsNotNone(forecast_one)
        self.assertIsNotNone(forecast_two)
        self.assertEqual(fallback.calls, 1)


if __name__ == "__main__":
    unittest.main()
