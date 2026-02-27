from __future__ import annotations

import asyncio
import logging

import aiohttp

from bot import create_bot, create_dispatcher
from config import load_settings
from database import AesGcmCoordinateCipher
from handlers import configure_handlers, get_bot_commands
from logging_setup import setup_logging
from migrations.runner import run_migrations
from repositories.user_repo import UserRepository
from scheduler import setup_scheduler
from services.alert_engine import AlertEngine
from services.ai_service import AiService
from services.weather_service import OpenMeteoProvider, OpenWeatherProvider, WeatherService


LOGGER = logging.getLogger(__name__)


async def main() -> None:
    setup_logging(level=logging.INFO)
    settings = load_settings()

    await run_migrations(settings.db_path)

    try:
        cipher = AesGcmCoordinateCipher(settings.location_enc_key)
    except RuntimeError as exc:
        LOGGER.error("startup_failed", extra={"error": str(exc)})
        return

    user_repo = UserRepository(settings.db_path, cipher)

    migrated_count = await user_repo.migrate_plain_coordinates()
    LOGGER.info("coordinate_migration_done", extra={"migrated_users": migrated_count})

    async with aiohttp.ClientSession() as http_session:
        providers = []
        if settings.weather_api_key:
            providers.append(OpenWeatherProvider(settings.weather_api_key))
        providers.append(OpenMeteoProvider())

        weather_service = WeatherService(
            providers=providers,
            cache_ttl_seconds=settings.cache_ttl_seconds,
            retries=settings.request_retries,
            backoff_seconds=settings.request_backoff_seconds,
            timeout_seconds=settings.request_timeout_seconds,
            connect_timeout_seconds=settings.request_connect_timeout_seconds,
        )

        alert_engine = AlertEngine()
        ai_service = AiService(settings.gemini_api_key)

        bot = create_bot(settings.bot_token)
        dp = create_dispatcher()

        configure_handlers(
            user_repo=user_repo,
            weather_service=weather_service,
            http_session=http_session,
            alert_engine=alert_engine,
            ai_service=ai_service,
            morning_hour=settings.morning_hour,
            morning_minute=settings.morning_minute,
            evening_hour=settings.evening_hour,
            evening_minute=settings.evening_minute,
        )

        try:
            await bot.set_my_commands(get_bot_commands())
        except Exception as exc:
            LOGGER.warning("failed_to_set_commands", extra={"error": str(exc)})

        scheduler = setup_scheduler(
            bot=bot,
            user_repo=user_repo,
            weather_service=weather_service,
            alert_engine=alert_engine,
            http_session=http_session,
            timezone_name=settings.timezone_name,
            morning_hour=settings.morning_hour,
            morning_minute=settings.morning_minute,
            evening_hour=settings.evening_hour,
            evening_minute=settings.evening_minute,
            severe_interval_minutes=settings.severe_interval_minutes,
        )
        scheduler.start()

        LOGGER.info("bot_start_polling")

        try:
            await dp.start_polling(bot)
        finally:
            scheduler.shutdown()
            await bot.session.close()
            LOGGER.info("bot_stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
