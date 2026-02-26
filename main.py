import asyncio
import logging
from bot import dp, bot
from database import init_db
from scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO)

async def main():
    # 1. Initialize DB
    await init_db()
    logging.info("Database initialized.")

    # 2. Setup and Start Scheduler
    scheduler = setup_scheduler()
    scheduler.start()
    logging.info("Scheduler started.")

    # 3. Start Bot Polling
    logging.info("Bot started polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
