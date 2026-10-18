import pandas as pd

from fxbot.backtest import run_backtest
from fxbot.config import BacktestConfig, RiskConfig
from fxbot.data import load_csv, synthetic_ohlc
from fxbot.strategies import BUY, NONE, Strategy, create_strategy


class OneShot(Strategy):
    """指定した足で 1 回だけシグナルを出すテスト用戦略。"""

    def __init__(self, at, direction=BUY):
        super().__init__(at=at)
        self.at, self.direction = at, direction

    @property
    def min_bars(self):
        return 1

    def signals(self, df):
        s = pd.Series(NONE, index=df.index, dtype=int)
        s.iloc[self.at] = self.direction
        return s


def flat_then(move, n_flat=30, n_move=10):
    rows = [(150.0, 150.25, 149.75, 150.0)] * n_flat
    price = 150.0
    for _ in range(n_move):
        nxt = price + move
        rows.append((price, max(price, nxt) + 0.05, min(price, nxt) - 0.05, nxt))
        price = nxt
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"],
                        index=pd.date_range("2024-01-01", periods=len(rows), freq="h"))


RISK = RiskConfig(sl_atr_mult=2.0, tp_atr_mult=3.0, atr_period=14, max_daily_loss_pct=0)
BT = BacktestConfig(initial_balance=1_000_000, spread_pips=0.3)


def test_buy_hits_take_profit():
    df = flat_then(+0.5)
    res = run_backtest(df, OneShot(29, 1), RISK, BT, "USDJPY")
    t = res.trades[0]
    assert t.reason == "take_profit"
    assert t.entry_time == df.index[30]          # 次の足の始値で約定
    assert t.entry_price == 150.0 + 0.003        # Ask = Bid + spread
    assert t.pnl > 0


def test_buy_hits_stop_loss_with_about_one_percent_loss():
    df = flat_then(-0.5)
    res = run_backtest(df, OneShot(29, 1), RISK, BT, "USDJPY")
    t = res.trades[0]
    assert t.reason == "stop_loss"
    assert -11_000 < t.pnl < -9_000


def test_sell_hits_take_profit():
    df = flat_then(-0.5)
    res = run_backtest(df, OneShot(29, -1), RISK, BT, "USDJPY")
    assert res.trades[0].reason == "take_profit" and res.trades[0].pnl > 0


def test_full_run_is_consistent():
    df = synthetic_ohlc(3000, seed=1)
    for name in ("ma_cross", "rsi_reversal"):
        res = run_backtest(df, create_strategy(name), RiskConfig(), BacktestConfig(), "USDJPY")
        assert res.stats["取引回数"] == len(res.trades) > 0
        total = sum(t.pnl for t in res.trades)
        assert abs(res.equity.iloc[-1] - (BT.initial_balance + total)) < 1e-6
        assert res.stats["最大ドローダウン(%)"] <= 0


def test_load_mt5_export_csv(tmp_path):
    p = tmp_path / "mt5.csv"
    p.write_text(
        "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"
        "2024.01.02\t00:00:00\t141.0\t141.5\t140.9\t141.2\t100\t0\t3\n"
        "2024.01.02\t01:00:00\t141.2\t141.3\t141.0\t141.1\t100\t0\t3\n"
    )
    df = load_csv(str(p))
    assert list(df.columns) == ["open", "high", "low", "close"]
    assert df.index[1] == pd.Timestamp("2024-01-02 01:00")
