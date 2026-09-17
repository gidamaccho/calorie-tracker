from datetime import datetime, timezone

import pytest

from fxbot.models import (
    Candle, EURUSD, Instrument, Position, Side, Signal, SignalType, Trade, USDJPY,
)

T = datetime(2024, 3, 4, tzinfo=timezone.utc)


def test_pip_conversion_jpy_vs_non_jpy():
    assert USDJPY.pips_to_price(10) == pytest.approx(0.10)
    assert USDJPY.price_to_pips(0.25) == pytest.approx(25.0)
    assert EURUSD.pips_to_price(10) == pytest.approx(0.0010)


def test_round_units_floors_to_step_and_rejects_below_minimum():
    inst = Instrument("USD/JPY", min_units=1000, units_step=1000)
    assert inst.round_units(12_999) == 12_000
    assert inst.round_units(999) == 0
    assert inst.round_units(1000) == 1000


def test_candle_rejects_impossible_ohlc():
    with pytest.raises(ValueError):
        Candle(T, open=150.0, high=149.0, low=148.0, close=148.5)  # high < open


def test_position_pnl_direction():
    long = Position(USDJPY, Side.BUY, 10_000, 150.0, T)
    short = Position(USDJPY, Side.SELL, 10_000, 150.0, T)
    # 1円 = 100pips 上昇
    assert long.unrealized_pnl(151.0) == pytest.approx(10_000)
    assert short.unrealized_pnl(151.0) == pytest.approx(-10_000)
    assert long.unrealized_pnl(149.0) == pytest.approx(-10_000)


def test_non_jpy_pair_uses_conversion_rate():
    position = Position(EURUSD, Side.BUY, 10_000, 1.0800, T)
    # +100pips = +0.01 USD/単位 → 100 USD。USD/JPY=150 なら 15,000円
    assert position.unrealized_pnl(1.0900, jpy_rate=150.0) == pytest.approx(15_000)


def test_required_margin_uses_leverage_cap():
    position = Position(USDJPY, Side.BUY, 25_000, 150.0, T)
    assert position.notional(150.0) == pytest.approx(3_750_000)
    assert position.required_margin(150.0) == pytest.approx(150_000)  # 25倍


def test_trade_pips_sign_matches_side():
    win_long = Trade(USDJPY, Side.BUY, 10_000, 150.0, 150.5, T, T, 5000)
    win_short = Trade(USDJPY, Side.SELL, 10_000, 150.0, 149.5, T, T, 5000)
    assert win_long.pips == pytest.approx(50.0)
    assert win_short.pips == pytest.approx(50.0)
    assert win_long.is_win and win_short.is_win


def test_signal_side_mapping():
    assert Signal(SignalType.ENTRY_LONG).side is Side.BUY
    assert Signal(SignalType.ENTRY_SHORT).side is Side.SELL
    assert Signal(SignalType.EXIT).side is None
    assert not Signal.none().is_entry


def test_trailing_best_price_tracks_favourable_direction_only():
    long = Position(USDJPY, Side.BUY, 1000, 150.0, T)
    long.update_trailing(151.0)
    long.update_trailing(150.2)
    assert long.best_price == pytest.approx(151.0)

    short = Position(USDJPY, Side.SELL, 1000, 150.0, T)
    short.update_trailing(149.0)
    short.update_trailing(149.8)
    assert short.best_price == pytest.approx(149.0)
