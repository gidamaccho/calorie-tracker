import pytest

from fxbot.indicators import (
    atr, bollinger, crossed_down, crossed_up, ema, highest, lowest, macd, rsi,
    sma, stdev, true_range,
)
from tests.conftest import make_candles


def test_sma_matches_manual_calculation():
    values = [1, 2, 3, 4, 5]
    result = sma(values, 3)
    assert result[:2] == [None, None]
    assert result[2] == pytest.approx(2.0)
    assert result[4] == pytest.approx(4.0)
    assert len(result) == len(values)


def test_indicators_return_none_until_enough_data():
    """先頭を None で埋めることで、未来の値を覗く事故を防いでいる。"""
    values = list(range(10))
    for series in (sma(values, 5), ema(values, 5), stdev(values, 5)):
        assert series[:4] == [None] * 4
        assert series[4] is not None


def test_ema_weights_recent_values_more_than_sma():
    values = [10.0] * 20 + [20.0] * 5
    assert ema(values, 10)[-1] > sma(values, 10)[-1]


def test_rsi_bounds_and_extremes():
    rising = [float(i) for i in range(1, 40)]
    assert rsi(rising, 14)[-1] == pytest.approx(100.0)

    falling = [float(i) for i in range(40, 1, -1)]
    assert rsi(falling, 14)[-1] == pytest.approx(0.0, abs=1e-9)

    mixed = [10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11]
    value = rsi(mixed, 14)[-1]
    assert 0.0 <= value <= 100.0


def test_true_range_includes_gap_from_previous_close():
    candles = make_candles([100.0, 110.0], wick=0.0)
    tr = true_range(candles)
    # 2本目は始値100/終値110、前足終値も100なので値幅は10
    assert tr[1] == pytest.approx(10.0)


def test_atr_is_positive_and_starts_after_period():
    candles = make_candles([100 + (i % 5) for i in range(30)])
    result = atr(candles, 14)
    assert result[12] is None
    assert result[13] is not None
    assert all(v > 0 for v in result[13:])


def test_bollinger_band_ordering():
    values = [100 + (i % 7) for i in range(40)]
    upper, mid, lower = bollinger(values, 20, 2.0)
    assert lower[-1] < mid[-1] < upper[-1]


def test_macd_histogram_is_difference_of_lines():
    values = [100 + i * 0.5 for i in range(80)]
    line, signal, hist = macd(values)
    idx = -1
    assert hist[idx] == pytest.approx(line[idx] - signal[idx])


def test_highest_lowest_window():
    values = [5, 3, 9, 1, 7]
    assert highest(values, 3)[-1] == 9
    assert lowest(values, 3)[-1] == 1


def test_cross_detection_requires_actual_crossing():
    fast = [None, 1.0, 3.0]
    slow = [None, 2.0, 2.0]
    assert crossed_up(fast, slow, 2)
    assert not crossed_down(fast, slow, 2)
    assert crossed_down(slow, fast, 2)
    # None が混ざる区間ではクロス判定しない
    assert not crossed_up(fast, slow, 1)


def test_cross_ignores_touching_without_crossing():
    fast = [1.0, 2.0, 2.0]
    slow = [2.0, 2.0, 2.0]
    assert not crossed_up(fast, slow, 2)  # 接触しただけで上抜けていない


def test_period_validation():
    with pytest.raises(ValueError):
        sma([1, 2, 3], 0)
