from datetime import datetime, timedelta, timezone

import pytest

from fxbot.brokers.base import BrokerError
from fxbot.brokers.paper import PaperBroker
from fxbot.models import Candle, Order, Side, USDJPY

T = datetime(2024, 3, 4, tzinfo=timezone.utc)


def broker(**kwargs):
    params = dict(starting_balance=1_000_000.0, spread_pips=0.4, slippage_pips=0.2)
    params.update(kwargs)
    b = PaperBroker(**params)
    b.connect()
    b.set_market(USDJPY, Candle(T, 150.0, 150.1, 149.9, 150.0))
    return b


def test_buy_fills_above_mid_and_sell_below():
    """買いはAsk+スリッページ、売りはBid-スリッページ。常に不利側。"""
    b = broker()
    long = b.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.0))
    assert long.entry_price == pytest.approx(150.0 + 0.002 + 0.002)

    b2 = broker()
    short = b2.place_order(Order(USDJPY, Side.SELL, 10_000, stop_price=151.0))
    assert short.entry_price == pytest.approx(150.0 - 0.002 - 0.002)


def test_round_trip_at_unchanged_price_loses_the_spread():
    """値動きゼロでも往復するとコスト分マイナスになること。"""
    b = broker()
    position = b.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.0))
    trade = b.close_position(position, "テスト")
    assert trade.pnl < 0
    # 往復のスプレッド+スリッページ = 0.008円 × 10000通貨 = 80円
    assert trade.pnl == pytest.approx(-80.0, abs=1.0)


def test_stop_loss_triggers_when_low_touches_level():
    b = broker()
    b.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.50))
    closed = b.process_candle(
        Candle(T + timedelta(hours=1), 150.0, 150.1, 149.40, 149.60), USDJPY
    )
    assert len(closed) == 1
    assert closed[0].exit_reason == "損切り"
    assert closed[0].pnl < 0


def test_take_profit_triggers_when_high_touches_level():
    b = broker()
    b.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.5, take_profit_price=150.50))
    closed = b.process_candle(
        Candle(T + timedelta(hours=1), 150.0, 150.60, 149.95, 150.40), USDJPY
    )
    assert len(closed) == 1
    assert closed[0].exit_reason == "利確"
    assert closed[0].pnl > 0


def test_stop_wins_when_one_candle_hits_both_levels():
    """同じ足で両方に触れたら損切り優先。成績を甘く見積もらないため。"""
    b = broker()
    b.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.50, take_profit_price=150.50))
    closed = b.process_candle(
        Candle(T + timedelta(hours=1), 150.0, 150.80, 149.20, 150.0), USDJPY
    )
    assert closed[0].exit_reason == "損切り"


def test_short_stop_triggers_on_high():
    b = broker()
    b.place_order(Order(USDJPY, Side.SELL, 10_000, stop_price=150.50))
    closed = b.process_candle(
        Candle(T + timedelta(hours=1), 150.0, 150.70, 149.9, 150.2), USDJPY
    )
    assert closed[0].exit_reason == "損切り"
    assert closed[0].pnl < 0


def test_stop_fill_includes_adverse_slippage():
    """損切りは指定値より不利な価格で約定する (窓開けを想定)。"""
    b = broker(slippage_pips=1.0)
    b.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.50))
    closed = b.process_candle(
        Candle(T + timedelta(hours=1), 150.0, 150.0, 149.0, 149.2), USDJPY
    )
    assert closed[0].exit_price == pytest.approx(149.50 - 0.01)


def test_equity_reflects_unrealized_pnl():
    b = broker()
    b.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.0))
    b.set_market(USDJPY, Candle(T + timedelta(hours=1), 150.0, 151.1, 150.0, 151.0))
    # 約定150.004 → 151.0 で +9,960円
    assert b.get_equity() == pytest.approx(1_000_000 + 9_960, abs=5)


def test_commission_is_charged_on_both_sides():
    b = broker(commission_per_10k=30.0)
    position = b.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.0))
    trade = b.close_position(position, "テスト")
    # 入口で30円、出口で30円
    assert trade.pnl == pytest.approx(-80.0 - 60.0, abs=1.0)


def test_swap_accrues_per_day_held():
    b = broker(swap_per_10k_per_day=10.0)
    position = b.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.0))
    b.set_market(USDJPY, Candle(T + timedelta(days=3), 150.0, 150.1, 149.9, 150.0))
    trade = b.close_position(position, "テスト")
    assert trade.pnl == pytest.approx(-80.0 - 30.0, abs=1.0)


def test_balance_only_changes_on_close():
    b = broker()
    position = b.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.0))
    assert b.balance == pytest.approx(1_000_000)
    b.close_position(position, "テスト")
    assert b.balance != pytest.approx(1_000_000)


def test_rejects_zero_units_and_missing_market():
    b = broker()
    with pytest.raises(BrokerError):
        b.place_order(Order(USDJPY, Side.BUY, 0))

    fresh = PaperBroker()
    fresh.connect()
    with pytest.raises(BrokerError):
        fresh.place_order(Order(USDJPY, Side.BUY, 1000))


def test_double_close_is_rejected():
    b = broker()
    position = b.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.0))
    b.close_position(position, "1回目")
    with pytest.raises(BrokerError):
        b.close_position(position, "2回目")


def test_close_all_clears_positions():
    b = broker(starting_balance=5_000_000.0)
    b.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.0))
    b.place_order(Order(USDJPY, Side.SELL, 10_000, stop_price=151.0))
    trades = b.close_all("緊急停止")
    assert len(trades) == 2
    assert b.get_positions() == []


def test_sum_of_trade_pnl_equals_balance_change():
    """成績指標が残高と食い違わないこと。

    手数料の一部を trade.pnl の外で引いてしまうと、プロフィットファクタや
    期待値が実態とずれる。ここが崩れたら指標は信用できない。
    """
    b = broker(commission_per_10k=30.0, swap_per_10k_per_day=5.0)
    for _ in range(3):
        position = b.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.0))
        b.set_market(USDJPY, Candle(T + timedelta(days=1), 150.2, 150.3, 150.1, 150.2))
        b.close_position(position, "テスト")
        b.set_market(USDJPY, Candle(T, 150.0, 150.1, 149.9, 150.0))

    assert sum(t.pnl for t in b.trades) == pytest.approx(b.balance - 1_000_000, abs=0.01)
