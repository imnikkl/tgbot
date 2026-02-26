import aiosqlite
import os

DB_PATH = 'weather_bot.db'

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL
            )
        ''')
        await db.commit()

async def upsert_user(user_id: int, chat_id: int, latitude: float, longitude: float):
    """
    Inserts a new user or updates their location if they already exist.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO users (user_id, chat_id, latitude, longitude)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                chat_id=excluded.chat_id,
                latitude=excluded.latitude,
                longitude=excluded.longitude
        ''', (user_id, chat_id, latitude, longitude))
        await db.commit()

async def get_all_users() -> list[dict]:
    """
    Returns a list of all users as dictionaries.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM users') as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_user(user_id: int) -> dict | None:
    """
    Returns a specific user's data or None.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
