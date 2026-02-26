CREATE TABLE IF NOT EXISTS schema_migrations (
    id TEXT PRIMARY KEY,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_rules (
    user_id INTEGER PRIMARY KEY,
    rain_mm_3h_threshold REAL NOT NULL DEFAULT 2.0,
    snow_mm_3h_threshold REAL NOT NULL DEFAULT 1.0,
    wind_ms_threshold REAL NOT NULL DEFAULT 13.0,
    min_temp_c_threshold REAL NOT NULL DEFAULT 0.0,
    max_temp_c_threshold REAL NOT NULL DEFAULT 35.0,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sent_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_key TEXT NOT NULL,
    sent_at_utc TEXT NOT NULL,
    UNIQUE(user_id, event_key),
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sent_alerts_user_time
ON sent_alerts (user_id, sent_at_utc);
