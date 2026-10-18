import pandas as pd
import pytest

from fxbot.broker import Position, SymbolSpec
from fxbot.config import Config
from fxbot.live import Trader, check_account_allowed
from fxbot.strategies import BUY, NONE, SELL, Strategy


class Scripted(Strategy):
    """最後の足に対して、外から決めたシグナルを返す。"""

    def __init__(self):
        super().__init__()
        self.next = NONE

    @property
    def min_bars(self):
        return 1

    def signals(self, df):
        s = pd.Series(NONE, index=df.index, dtype=int)
        s.iloc[-1] = self.next
        return s


class FakeBroker:
    def __init__(self, demo=True):
        self.demo = demo
        self.bars = 100
        self.pos = None
        self.orders = []

    def is_demo(self):
        return self.demo

    def account_summary(self):
        return "fake"

    def symbol_spec(self, symbol):
        return SymbolSpec(0.001, 3, 0.01, 50, 0.01, 100_000)

    def equity(self):
        return 1_000_000

    def bid_ask(self, symbol):
        return 150.000, 150.003

    def closed_bars(self, symbol, tf, count):
        idx = pd.date_range("2024-01-01", periods=self.bars, freq="h")
        return pd.DataFrame({"open": 150.0, "high": 150.25, "low": 149.75, "close": 150.0}, index=idx)

    def position(self, symbol, magic):
        return self.pos

    def open(self, symbol, direction, lots, sl, tp, magic, deviation):
        self.orders.append(("open", direction, lots, sl, tp))
        self.pos = Position(1, direction, lots, 150.0)

    def close(self, symbol, pos, magic, deviation):
        self.orders.append(("close", pos.ticket))
        self.pos = None


def make(demo=True):
    broker, strat = FakeBroker(demo), Scripted()
    trader = Trader(broker, strat, Config())
    trader.start()
    return broker, strat, trader


def test_refuses_real_account(monkeypatch):
    monkeypatch.delenv("FXBOT_ALLOW_LIVE", raising=False)
    cfg = Config()
    with pytest.raises(RuntimeError):
        check_account_allowed(FakeBroker(demo=False), cfg)
    cfg.live.allow_live_account = True
    with pytest.raises(RuntimeError):  # 環境変数が無ければまだ拒否
        check_account_allowed(FakeBroker(demo=False), cfg)
    monkeypatch.setenv("FXBOT_ALLOW_LIVE", "yes")
    check_account_allowed(FakeBroker(demo=False), cfg)


def test_ignores_signal_on_startup_bar_and_same_bar():
    broker, strat, trader = make()
    strat.next = BUY
    trader.step()           # 起動時の足は見送り
    assert broker.orders == []
    broker.bars += 1
    trader.step()           # 新しい足 → 発注
    trader.step()           # 同じ足 → 何もしない
    assert len(broker.orders) == 1
    kind, direction, lots, sl, tp = broker.orders[0]
    assert (kind, direction) == ("open", BUY)
    assert sl < 150.003 < tp
    assert lots > 0


def test_reverse_on_opposite_signal():
    broker, strat, trader = make()
    trader.step()
    strat.next = BUY
    broker.bars += 1
    trader.step()
    strat.next = SELL
    broker.bars += 1
    trader.step()
    assert [o[0] for o in broker.orders] == ["open", "close", "open"]
    assert broker.pos.direction == SELL


def test_dry_run_sends_nothing():
    broker, strat, trader = make()
    trader.cfg.live.dry_run = True
    trader.step()
    strat.next = BUY
    broker.bars += 1
    trader.step()
    assert broker.orders == []
