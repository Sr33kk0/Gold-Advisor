-- Daily global benchmark spot prices (one row per day).
CREATE TABLE IF NOT EXISTS spot_prices (
    date               TEXT PRIMARY KEY,
    gold_rate_per_oz   REAL NOT NULL,
    silver_rate_per_oz REAL NOT NULL,
    fetched_at         TIMESTAMP NOT NULL
);

-- Personal trade ledger.
CREATE TABLE IF NOT EXISTS transactions (
    id                 TEXT PRIMARY KEY,
    timestamp          TIMESTAMP NOT NULL,
    action_type        TEXT NOT NULL CHECK (action_type IN ('BUY', 'SELL')),
    metal              TEXT NOT NULL CHECK (metal IN ('GOLD', 'SILVER')),
    execution_rate_myr REAL NOT NULL,
    mass_grams         REAL NOT NULL,
    fiat_total_myr     REAL NOT NULL
);

-- Daily AI sentiment cache (worker-computed, UI-read).
CREATE TABLE IF NOT EXISTS sentiment_snapshots (
    date                 TEXT PRIMARY KEY,
    sentiment_score      REAL NOT NULL,
    dominant_risk_factor TEXT,
    analytical_summary   TEXT,
    source_headlines     TEXT,
    fetched_at           TIMESTAMP NOT NULL
);

-- Key/value runtime configuration.
CREATE TABLE IF NOT EXISTS system_settings (
    config_key   TEXT PRIMARY KEY,
    config_value TEXT NOT NULL
);

-- Manually recorded daily platform price quotes (one row per day per metal).
-- Reference data, not capital events: correctable by overwrite/delete.
CREATE TABLE IF NOT EXISTS daily_quotes (
    date          TEXT NOT NULL,
    metal         TEXT NOT NULL CHECK (metal IN ('GOLD', 'SILVER')),
    buy_rate_myr  REAL NOT NULL,
    sell_rate_myr REAL NOT NULL,
    recorded_at   TIMESTAMP NOT NULL,
    PRIMARY KEY (date, metal)
);
