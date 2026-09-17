import json

import pytest

from fxbot.cli import main
from fxbot.feeds import SyntheticFeed, write_csv


def test_backtest_runs_and_prints_summary(capsys):
    assert main(["backtest", "--bars", "600", "--seed", "3", "--log-level", "ERROR"]) == 0
    out = capsys.readouterr().out
    assert "バックテスト結果" in out
    assert "最大DD" in out


def test_backtest_with_csv(tmp_path, capsys):
    path = str(tmp_path / "d.csv")
    write_csv(SyntheticFeed(bars=800, seed=4).to_list(), path)
    assert main(["backtest", "--csv", path, "--strategy", "breakout",
                 "--log-level", "ERROR"]) == 0
    assert "ブレイクアウト" in capsys.readouterr().out


def test_backtest_errors_when_data_shorter_than_warmup(tmp_path, capsys):
    path = str(tmp_path / "d.csv")
    write_csv(SyntheticFeed(bars=30, seed=4).to_list(), path)
    assert main(["backtest", "--csv", path, "--strategy", "sma_cross",
                 "--log-level", "CRITICAL"]) == 1


def test_optimize_lists_results(capsys):
    code = main([
        "optimize", "--bars", "700", "--seed", "5", "--strategy", "breakout",
        "--param", "entry_period=10,20", "--param", "exit_period=5",
        "--top", "5", "--log-level", "ERROR",
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "entry_period=10" in out
    assert "過剰適合" in out  # 警告が出ていること


def test_optimize_requires_params(capsys):
    assert main(["optimize", "--bars", "200", "--log-level", "CRITICAL"]) == 1


def test_optimize_rejects_malformed_param(capsys):
    assert main(["optimize", "--bars", "200", "--param", "fast", "--log-level", "CRITICAL"]) == 1


def test_fetch_synthetic_writes_csv(tmp_path, capsys):
    out = str(tmp_path / "out.csv")
    assert main(["fetch", "--synthetic", "--bars", "100", "--out", out,
                 "--log-level", "ERROR"]) == 0
    from fxbot.feeds import CsvFeed
    assert len(CsvFeed(out).load()) == 100


def test_live_refuses_without_risk_acknowledgement(tmp_path, capsys):
    config = tmp_path / "c.json"
    config.write_text(json.dumps({"broker": "sbi_web", "broker_params": {
        "dry_run": False, "confirm_live_trading": True,
        "selectors": {k: "#x" for k in (
            "username_input", "password_input", "login_button", "fx_menu_link",
            "symbol_selector", "units_input", "buy_button", "sell_button",
            "confirm_button", "bid_price", "ask_price", "equity_value",
            "position_rows")},
    }}), encoding="utf-8")

    code = main(["live", "--config", str(config), "--log-level", "CRITICAL"])
    assert code == 2
    assert "i-understand-the-risks" in capsys.readouterr().err


def test_bad_config_path_returns_error(capsys):
    assert main(["backtest", "--config", "/no/such/file.json"]) == 1
    assert "エラー" in capsys.readouterr().err


def test_unknown_strategy_is_rejected_by_argparse():
    with pytest.raises(SystemExit):
        main(["backtest", "--strategy", "存在しない"])
