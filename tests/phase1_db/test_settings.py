from database.connection import (
    DEFAULT_SETTINGS,
    get_setting,
    seed_default_settings,
    set_setting,
)


def test_set_then_get(db_conn):
    set_setting(db_conn, "rsi_period", "21")
    assert get_setting(db_conn, "rsi_period") == "21"


def test_get_missing_returns_default(db_conn):
    assert get_setting(db_conn, "does_not_exist") is None
    assert get_setting(db_conn, "does_not_exist", "fallback") == "fallback"


def test_set_setting_upserts(db_conn):
    set_setting(db_conn, "rsi_period", "14")
    set_setting(db_conn, "rsi_period", "28")
    rows = db_conn.execute(
        "SELECT config_value FROM system_settings WHERE config_key=?;",
        ("rsi_period",),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["config_value"] == "28"


def test_seed_populates_known_keys(db_conn):
    seed_default_settings(db_conn)
    assert get_setting(db_conn, "rsi_oversold") == "30"
    assert get_setting(db_conn, "rsi_overbought") == "70"
    assert get_setting(db_conn, "TIMEZONE") == "Asia/Kuala_Lumpur"
    assert get_setting(db_conn, "BASE_CURRENCY") == "MYR"


def test_seed_does_not_overwrite_existing(db_conn):
    set_setting(db_conn, "rsi_period", "99")
    seed_default_settings(db_conn)
    assert get_setting(db_conn, "rsi_period") == "99"


def test_seed_includes_gemini_model_default(db_conn):
    seed_default_settings(db_conn)
    assert get_setting(db_conn, "GEMINI_MODEL") == "gemini-3-flash-preview"


def test_default_settings_has_all_expected_keys():
    expected = {
        "default_buy_spread", "default_sell_spread",
        "rsi_period", "rsi_oversold", "rsi_overbought",
        "vol_band_deviations", "gsr_band_deviations",
        "quant_vote_threshold", "sentiment_max_age_days",
        "BASE_CURRENCY", "TIMEZONE",
    }
    assert expected <= set(DEFAULT_SETTINGS)


def test_risk_policy_defaults_seeded(db_conn):
    seed_default_settings(db_conn)
    assert get_setting(db_conn, "stop_loss_pct") == "5.0"
    assert get_setting(db_conn, "take_profit_pct") == "10.0"
    assert get_setting(db_conn, "max_position_grams") == "100.0"
