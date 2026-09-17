import json
import os
from datetime import datetime, timezone

import pytest

from fxbot.brokers import build_broker
from fxbot.brokers.base import BrokerError
from fxbot.brokers.sbi_web import SbiWebBroker, SbiWebConfig
from fxbot.config import AppConfig, load_config
from fxbot.feeds import CsvFeed, SyntheticFeed, write_csv
from fxbot.journal import Journal


# --- 設定 ---------------------------------------------------------------

def write_config(tmp_path, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_defaults_when_no_config_given():
    config = load_config(None)
    assert config.symbol == "USD/JPY"
    assert config.broker == "paper"


def test_missing_file_is_an_error():
    with pytest.raises(FileNotFoundError):
        load_config("/存在しない/config.json")


def test_unknown_top_level_key_is_rejected(tmp_path):
    """typo を黙って無視すると、設定したつもりの値が効かない事故になる。"""
    path = write_config(tmp_path, {"symbl": "USD/JPY"})
    with pytest.raises(ValueError, match="未知の設定キー"):
        load_config(path)


def test_unknown_risk_key_is_rejected(tmp_path):
    path = write_config(tmp_path, {"risk": {"risk_per_trad": 0.01}})
    with pytest.raises(ValueError, match="未知のキー"):
        load_config(path).risk_config()


def test_secrets_in_config_file_are_rejected(tmp_path):
    """認証情報の直書きを拒否する。誤ってコミットされるのを防ぐ。"""
    path = write_config(tmp_path, {"broker_params": {"password": "秘密"}})
    with pytest.raises(ValueError, match="認証情報"):
        load_config(path)


def test_env_var_name_keys_are_allowed(tmp_path):
    """`..._env` は環境変数名なので、値そのものではない。"""
    path = write_config(tmp_path, {"broker_params": {"password_env": "SBI_PASSWORD"}})
    config = load_config(path)
    assert config.broker_params["password_env"] == "SBI_PASSWORD"


def test_instrument_inferred_for_unknown_symbol():
    assert AppConfig(symbol="AUD/JPY").instrument().pip == pytest.approx(0.01)
    assert AppConfig(symbol="GBP/USD").instrument().pip == pytest.approx(0.0001)
    assert AppConfig(symbol="GBP/USD").instrument().quote_is_jpy is False


def test_instrument_overrides_apply():
    config = AppConfig(symbol="USD/JPY", instrument_overrides={"min_units": 10_000})
    assert config.instrument().min_units == 10_000


def test_trading_hours_list_becomes_tuple(tmp_path):
    path = write_config(tmp_path, {"risk": {"trading_hours": [7, 20]}})
    assert load_config(path).risk_config().trading_hours == (7, 20)


# --- データ -------------------------------------------------------------

def test_csv_round_trip(tmp_path):
    candles = SyntheticFeed(bars=50, seed=1).to_list()
    path = str(tmp_path / "data.csv")
    assert write_csv(candles, path) == 50

    loaded = CsvFeed(path).load()
    assert len(loaded) == 50
    assert loaded[0].close == pytest.approx(candles[0].close)
    assert loaded[-1].time == candles[-1].time


def test_csv_accepts_various_time_formats(tmp_path):
    path = tmp_path / "d.csv"
    path.write_text(
        "date,open,high,low,close\n"
        "2024-03-04 09:00:00,150.0,150.5,149.5,150.2\n"
        "2024-03-04T10:00:00Z,150.2,150.8,150.0,150.6\n"
        "1709550000,150.6,151.0,150.4,150.9\n",
        encoding="utf-8",
    )
    candles = CsvFeed(str(path)).load()
    assert len(candles) == 3
    assert all(c.time.tzinfo is not None for c in candles)


def test_csv_sorts_out_of_order_rows(tmp_path):
    path = tmp_path / "d.csv"
    path.write_text(
        "time,open,high,low,close\n"
        "2024-03-04T11:00:00Z,150.2,150.8,150.0,150.6\n"
        "2024-03-04T09:00:00Z,150.0,150.5,149.5,150.2\n",
        encoding="utf-8",
    )
    candles = CsvFeed(str(path)).load()
    assert candles[0].time < candles[1].time


def test_csv_missing_column_reports_which_one(tmp_path):
    path = tmp_path / "d.csv"
    path.write_text("time,open,high,close\n2024-03-04T09:00:00Z,1,2,3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="low"):
        CsvFeed(str(path)).load()


def test_csv_bad_row_reports_line_number(tmp_path):
    path = tmp_path / "d.csv"
    path.write_text(
        "time,open,high,low,close\n"
        "2024-03-04T09:00:00Z,150.0,150.5,149.5,150.2\n"
        "2024-03-04T10:00:00Z,abc,150.8,150.0,150.6\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=":3"):
        CsvFeed(str(path)).load()


def test_synthetic_feed_is_deterministic_for_a_seed():
    a = SyntheticFeed(bars=100, seed=99).to_list()
    b = SyntheticFeed(bars=100, seed=99).to_list()
    assert [c.close for c in a] == [c.close for c in b]


def test_synthetic_feed_skips_weekends():
    for candle in SyntheticFeed(bars=300, seed=1).to_list():
        assert candle.time.weekday() < 5


# --- SBI アダプタの安全装置 --------------------------------------------

def test_sbi_defaults_to_dry_run():
    assert SbiWebBroker(SbiWebConfig()).dry_run


def test_sbi_live_requires_explicit_confirmation():
    with pytest.raises(BrokerError, match="confirm_live_trading"):
        SbiWebBroker(SbiWebConfig(dry_run=False))


def test_sbi_live_requires_all_selectors():
    with pytest.raises(BrokerError, match="セレクタ未設定"):
        SbiWebBroker(SbiWebConfig(dry_run=False, confirm_live_trading=True))


def test_sbi_dry_run_never_places_real_orders():
    from fxbot.models import Order, Side, USDJPY

    broker = SbiWebBroker(SbiWebConfig())
    broker.connect()
    position = broker.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.0))
    assert broker.get_positions() == [position]
    trade = broker.close_position(position, "テスト")
    assert "[DRY-RUN]" in trade.exit_reason
    assert broker.get_positions() == []


def test_sbi_price_parsing_rejects_garbage():
    with pytest.raises(BrokerError):
        SbiWebBroker._parse_price("―")
    assert SbiWebBroker._parse_price(" 1,150.25 円 ") == pytest.approx(1150.25)


def test_oanda_live_requires_confirmation():
    with pytest.raises(BrokerError, match="confirm_live_trading"):
        build_broker("oanda", {"environment": "live"})


def test_unknown_broker_is_rejected():
    with pytest.raises(KeyError):
        build_broker("存在しない証券会社")


# --- 記録 ---------------------------------------------------------------

def test_journal_writes_trades_and_events(tmp_path):
    from fxbot.models import Side, Trade, USDJPY

    journal = Journal(str(tmp_path / "j"))
    trade = Trade(
        USDJPY, Side.BUY, 10_000, 150.0, 150.5,
        datetime(2024, 3, 4, tzinfo=timezone.utc),
        datetime(2024, 3, 4, 3, tzinfo=timezone.utc),
        pnl=5000.0, exit_reason="利確",
    )
    journal.record_trade(trade)
    journal.event("engine_start", equity=1_000_000)

    trades = open(journal.trades_path, encoding="utf-8").read()
    assert "利確" in trades and "5000.00" in trades
    events = open(journal.events_path, encoding="utf-8").read().splitlines()
    assert len(events) == 2  # trade_closed + engine_start
    assert json.loads(events[0])["kind"] == "trade_closed"


def test_journal_can_be_disabled(tmp_path):
    journal = Journal(str(tmp_path / "off"), enabled=False)
    journal.event("何か")
    assert not os.path.exists(journal.events_path)


def test_selector_names_are_not_mistaken_for_secrets(tmp_path):
    """CSSセレクタ名 (password_input など) は秘密情報ではない。

    ここを誤検知すると、正しい設定ファイルが読めなくなる。
    """
    path = write_config(tmp_path, {
        "broker_params": {
            "selectors": {"password_input": "#password", "username_input": "#user"},
            "password_env": "SBI_PASSWORD",
        }
    })
    config = load_config(path)
    assert config.broker_params["selectors"]["password_input"] == "#password"


def test_actual_secret_value_is_still_rejected(tmp_path):
    path = write_config(tmp_path, {"broker_params": {"api_token": "abc123"}})
    with pytest.raises(ValueError, match="認証情報"):
        load_config(path)


def test_underscore_keys_are_treated_as_comments(tmp_path):
    """JSONにはコメントが書けないので "_" 始まりのキーを注記として使える。"""
    path = write_config(tmp_path, {"_メモ": "これは注記", "symbol": "EUR/JPY"})
    assert load_config(path).symbol == "EUR/JPY"


def test_shipped_example_configs_all_load():
    """同梱の設定サンプルが実際に読めること。"""
    import glob
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    examples = sorted(glob.glob(os.path.join(here, "examples", "*.json")))
    assert examples
    for path in examples:
        config = load_config(path)
        config.instrument()
        config.risk_config()
        config.engine_config()
