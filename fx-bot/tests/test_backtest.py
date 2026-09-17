import pytest

from fxbot.backtest import run_backtest
from fxbot.feeds import SyntheticFeed
from fxbot.models import Signal, SignalType, USDJPY
from fxbot.risk import RiskConfig
from fxbot.strategies import build_strategy
from fxbot.strategies.base import Strategy
from tests.conftest import make_candles


class AlwaysLong(Strategy):
    """検証用: 建玉が無ければ必ず買う戦略。"""

    name = "always_long"

    def __init__(self, instrument, stop_pips=50.0, tp_pips=50.0):
        super().__init__(instrument)
        self.stop_pips = stop_pips
        self.tp_pips = tp_pips

    @property
    def warmup(self):
        return 2

    def on_candle(self, position):
        if position is not None or not self.ready:
            return Signal.none()
        price = self.candles[-1].close
        return Signal(
            SignalType.ENTRY_LONG,
            reason="テスト",
            stop_price=price - self.instrument.pips_to_price(self.stop_pips),
            take_profit_price=price + self.instrument.pips_to_price(self.tp_pips),
        )


class Silent(Strategy):
    name = "silent"

    @property
    def warmup(self):
        return 2

    def on_candle(self, position):
        return Signal.none()


def test_empty_data_is_rejected():
    with pytest.raises(ValueError):
        run_backtest([], Silent(USDJPY), USDJPY)


def test_silent_strategy_leaves_balance_untouched():
    candles = make_candles([150.0 + (i % 5) * 0.1 for i in range(100)])
    result = run_backtest(candles, Silent(USDJPY), USDJPY, starting_balance=1_000_000)
    assert result.total_trades == 0
    assert result.final_balance == pytest.approx(1_000_000)
    assert result.profit_factor == 0.0
    assert result.win_rate == 0.0


def test_metrics_are_internally_consistent():
    candles = SyntheticFeed(bars=1500, seed=11).to_list()
    result = run_backtest(
        candles,
        build_strategy("breakout", USDJPY, {"entry_period": 10, "exit_period": 5}),
        USDJPY,
        RiskConfig(max_consecutive_losses=999, daily_loss_limit=1.0, max_drawdown=0.99),
    )
    assert result.total_trades > 0
    # 損益の合計 = 残高の増減
    assert sum(t.pnl for t in result.trades) == pytest.approx(result.net_pnl, abs=0.01)
    assert len(result.wins) + len(result.losses) == result.total_trades
    assert result.gross_profit >= 0 and result.gross_loss >= 0
    assert result.net_pnl == pytest.approx(result.gross_profit - result.gross_loss, abs=0.01)
    assert 0 <= result.win_rate <= 100
    assert 0 <= result.max_drawdown <= 1


def test_profit_factor_and_expectancy_definitions():
    candles = SyntheticFeed(bars=1200, seed=5).to_list()
    result = run_backtest(
        candles,
        build_strategy("breakout", USDJPY, {"entry_period": 8, "exit_period": 4}),
        USDJPY,
        RiskConfig(max_consecutive_losses=999, daily_loss_limit=1.0, max_drawdown=0.99),
    )
    if result.gross_loss > 0:
        assert result.profit_factor == pytest.approx(result.gross_profit / result.gross_loss)
    assert result.expectancy == pytest.approx(result.net_pnl / result.total_trades)


def test_open_position_is_closed_at_end_of_period():
    candles = make_candles([150.0 + i * 0.01 for i in range(60)])
    result = run_backtest(candles, AlwaysLong(USDJPY), USDJPY, close_at_end=True)
    assert result.trades
    assert any(t.exit_reason == "検証期間終了" for t in result.trades)


def test_risk_halt_stops_further_entries():
    """連敗で停止したあと、新規建玉が入らないこと。"""
    # 一貫した下落 → 買い続ければ必ず損切りになる
    candles = make_candles([150.0 - i * 0.08 for i in range(300)])
    result = run_backtest(
        candles,
        AlwaysLong(USDJPY, stop_pips=20, tp_pips=200),
        USDJPY,
        RiskConfig(max_consecutive_losses=3, daily_loss_limit=1.0, max_drawdown=0.99),
    )
    assert result.halt_reason
    assert result.total_trades <= 4  # 3連敗+期間終了決済まで
    assert any("取引停止中" in reason for _, reason in result.blocked)


def test_costs_make_a_coin_flip_strategy_lose():
    """スプレッドがある以上、優位性の無い売買は負けること。"""
    # 上下に振れるだけの相場
    prices = []
    for i in range(400):
        prices.append(150.0 + (0.3 if i % 2 else -0.3))
    candles = make_candles(prices)
    result = run_backtest(
        candles,
        AlwaysLong(USDJPY, stop_pips=25, tp_pips=25),
        USDJPY,
        RiskConfig(max_consecutive_losses=999, daily_loss_limit=1.0, max_drawdown=0.99),
        spread_pips=2.0,
        slippage_pips=0.5,
    )
    assert result.net_pnl < 0


def test_equity_curve_tracks_every_bar():
    candles = make_candles([150.0 + (i % 7) * 0.05 for i in range(120)])
    result = run_backtest(candles, Silent(USDJPY), USDJPY)
    assert len(result.equity_curve) == len(candles)
    assert result.equity_curve[0][0] == candles[0].time


def test_max_drawdown_measured_from_running_peak():
    candles = make_candles([150.0] * 10)
    result = run_backtest(candles, Silent(USDJPY), USDJPY, starting_balance=1_000_000)
    result.equity_curve = [
        (candles[0].time, 1_000_000),
        (candles[1].time, 1_200_000),
        (candles[2].time, 900_000),   # ピーク120万から-25%
        (candles[3].time, 1_100_000),
    ]
    assert result.max_drawdown == pytest.approx(0.25)
    assert result.max_drawdown_yen == pytest.approx(300_000)


def test_summary_renders_without_error():
    candles = SyntheticFeed(bars=800, seed=3).to_list()
    result = run_backtest(candles, build_strategy("breakout", USDJPY), USDJPY)
    text = result.summary()
    assert "バックテスト結果" in text
    assert "プロフィットファクタ" in text
    assert result.trade_table(limit=5)
