from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiohttp
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from repositories.user_repo import UserRepository
from services.alert_engine import AlertEngine
from services.weather_service import WeatherService


LOGGER = logging.getLogger(__name__)


class WeatherScheduler:
    def __init__(
        self,
        *,
        bot: Bot,
        user_repo: UserRepository,
        weather_service: WeatherService,
        alert_engine: AlertEngine,
        http_session: aiohttp.ClientSession,
        timezone_name: str,
        morning_hour: int,
        morning_minute: int,
        evening_hour: int,
        evening_minute: int,
        severe_interval_minutes: int,
    ):
        self._bot = bot
        self._repo = user_repo
        self._weather_service = weather_service
        self._alert_engine = alert_engine
        self._http_session = http_session
        self._timezone_name = timezone_name

        tzinfo = ZoneInfo(timezone_name)
        self._scheduler = AsyncIOScheduler(timezone=tzinfo)
        self._scheduler.add_job(
            self._run_morning_briefing,
            "cron",
            hour=morning_hour,
            minute=morning_minute,
            id="morning_briefing",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_evening_briefing,
            "cron",
            hour=evening_hour,
            minute=evening_minute,
            id="evening_briefing",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_severe_scan,
            "interval",
            minutes=severe_interval_minutes,
            id="severe_scan",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._cleanup_sent_alerts,
            "cron",
            hour=3,
            minute=0,
            id="cleanup_sent_alerts",
            replace_existing=True,
        )

    def start(self) -> None:
        self._scheduler.start()
        LOGGER.info("Scheduler started", extra={"timezone": self._timezone_name})

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    async def _run_morning_briefing(self) -> None:
        await self._run_briefing(job_name="morning_briefing", flag_name="daily_morning_enabled")

    async def _run_evening_briefing(self) -> None:
        await self._run_briefing(job_name="evening_briefing", flag_name="daily_evening_enabled")

    async def _run_briefing(self, *, job_name: str, flag_name: str) -> None:
        users = await self._repo.get_all_users()
        now_utc = datetime.now(timezone.utc)

        sent_count = 0
        quiet_skipped = 0
        deduped_count = 0

        for user in users:
            if int(user.get(flag_name, 1)) != 1:
                continue

            forecast = await self._weather_service.get_forecast(
                user["latitude"], user["longitude"], self._http_session
            )
            if not forecast:
                continue

            prefs = self._alert_engine.prefs_from_user(user)

            quiet_now = self._alert_engine.is_quiet_now(
                now_utc,
                forecast.timezone_offset_seconds,
                prefs.quiet_start,
                prefs.quiet_end,
            )

            events = self._alert_engine.evaluate_events(
                forecast,
                prefs,
                now_utc=now_utc,
                hours=24,
                severe_only=False,
            )

            if quiet_now:
                allowed_events = []
                for event in events:
                    if event.severity == "severe" and prefs.severe_immediate_enabled:
                        allowed_events.append(event)
                        continue
                    quiet_skipped += 1
                events = allowed_events

            dedup_filtered: list = []
            for event in events:
                recently_sent = await self._repo.was_alert_sent_recently(
                    user_id=user["user_id"],
                    event_key=event.event_key,
                    cooldown_minutes=prefs.alert_cooldown_minutes,
                    now_utc=now_utc,
                )
                if recently_sent:
                    deduped_count += 1
                    continue
                dedup_filtered.append(event)

            if not dedup_filtered:
                continue

            message_text = self._alert_engine.render_briefing_message(
                dedup_filtered,
                city_name=forecast.city_name,
                period_hours=24,
            )

            try:
                await self._bot.send_message(chat_id=user["chat_id"], text=message_text)
                for event in dedup_filtered:
                    await self._repo.mark_alert_sent(user["user_id"], event.event_key, now_utc)
                sent_count += 1
            except Exception as exc:
                LOGGER.warning(
                    "Failed to send briefing",
                    extra={
                        "job_name": job_name,
                        "chat_id": user["chat_id"],
                        "user_id": user["user_id"],
                        "error": str(exc),
                    },
                )

        LOGGER.info(
            "briefing_completed",
            extra={
                "job_name": job_name,
                "metric": "alerts_sent",
                "alerts_sent": sent_count,
                "alerts_suppressed_quiet": quiet_skipped,
                "alerts_deduped": deduped_count,
            },
        )

    async def _run_severe_scan(self) -> None:
        users = await self._repo.get_all_users()
        now_utc = datetime.now(timezone.utc)

        sent_count = 0
        deduped_count = 0

        for user in users:
            if int(user.get("severe_immediate_enabled", 1)) != 1:
                continue

            forecast = await self._weather_service.get_forecast(
                user["latitude"], user["longitude"], self._http_session
            )
            if not forecast:
                continue

            prefs = self._alert_engine.prefs_from_user(user)
            events = self._alert_engine.evaluate_events(
                forecast,
                prefs,
                now_utc=now_utc,
                hours=6,
                severe_only=True,
            )

            for event in events:
                recently_sent = await self._repo.was_alert_sent_recently(
                    user_id=user["user_id"],
                    event_key=event.event_key,
                    cooldown_minutes=prefs.alert_cooldown_minutes,
                    now_utc=now_utc,
                )
                if recently_sent:
                    deduped_count += 1
                    continue

                message_text = self._alert_engine.render_severe_message(event, forecast.city_name)
                try:
                    await self._bot.send_message(chat_id=user["chat_id"], text=message_text)
                    await self._repo.mark_alert_sent(user["user_id"], event.event_key, now_utc)
                    sent_count += 1
                except Exception as exc:
                    LOGGER.warning(
                        "Failed to send severe alert",
                        extra={
                            "job_name": "severe_scan",
                            "chat_id": user["chat_id"],
                            "user_id": user["user_id"],
                            "error": str(exc),
                        },
                    )

        LOGGER.info(
            "severe_scan_completed",
            extra={
                "job_name": "severe_scan",
                "metric": "alerts_sent",
                "alerts_sent": sent_count,
                "alerts_deduped": deduped_count,
            },
        )

    async def _cleanup_sent_alerts(self) -> None:
        await self._repo.cleanup_old_alerts()


def setup_scheduler(
    *,
    bot: Bot,
    user_repo: UserRepository,
    weather_service: WeatherService,
    alert_engine: AlertEngine,
    http_session: aiohttp.ClientSession,
    timezone_name: str,
    morning_hour: int,
    morning_minute: int,
    evening_hour: int,
    evening_minute: int,
    severe_interval_minutes: int,
) -> WeatherScheduler:
    return WeatherScheduler(
        bot=bot,
        user_repo=user_repo,
        weather_service=weather_service,
        alert_engine=alert_engine,
        http_session=http_session,
        timezone_name=timezone_name,
        morning_hour=morning_hour,
        morning_minute=morning_minute,
        evening_hour=evening_hour,
        evening_minute=evening_minute,
        severe_interval_minutes=severe_interval_minutes,
    )
