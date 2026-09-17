"""テクニカル指標。すべて標準ライブラリのみで実装する。

各関数は「入力と同じ長さのリスト」を返し、計算できない先頭部分は None を入れる。
こうしておくと足のインデックスと指標のインデックスが常に一致し、
バックテストで未来の値を覗いてしまう事故 (look-ahead bias) を避けやすい。
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence

from .models import Candle

Series = List[Optional[float]]


def _check_period(period: int) -> None:
    if period < 1:
        raise ValueError(f"period は1以上が必要: {period}")


def sma(values: Sequence[float], period: int) -> Series:
    """単純移動平均。"""
    _check_period(period)
    out: Series = [None] * len(values)
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def ema(values: Sequence[float], period: int) -> Series:
    """指数平滑移動平均。初期値は先頭 period 本の SMA。"""
    _check_period(period)
    out: Series = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values: Sequence[float], period: int = 14) -> Series:
    """RSI (Wilder方式)。0-100。"""
    _check_period(period)
    out: Series = [None] * len(values)
    if len(values) <= period:
        return out

    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        diff = values[i] - values[i - 1]
        gains += max(diff, 0.0)
        losses += max(-diff, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi_from_averages(avg_gain, avg_loss)

    for i in range(period + 1, len(values)):
        diff = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(diff, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-diff, 0.0)) / period
        out[i] = _rsi_from_averages(avg_gain, avg_loss)
    return out


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def true_range(candles: Sequence[Candle]) -> Series:
    out: Series = [None] * len(candles)
    for i, c in enumerate(candles):
        if i == 0:
            out[i] = c.high - c.low
        else:
            prev_close = candles[i - 1].close
            out[i] = max(
                c.high - c.low,
                abs(c.high - prev_close),
                abs(c.low - prev_close),
            )
    return out


def atr(candles: Sequence[Candle], period: int = 14) -> Series:
    """平均真幅。ボラティリティに応じた損切り幅・ポジションサイズに使う。"""
    _check_period(period)
    tr = true_range(candles)
    out: Series = [None] * len(candles)
    if len(candles) < period:
        return out
    first = sum(v for v in tr[:period] if v is not None) / period
    out[period - 1] = first
    prev = first
    for i in range(period, len(candles)):
        cur = tr[i]
        assert cur is not None
        prev = (prev * (period - 1) + cur) / period
        out[i] = prev
    return out


def stdev(values: Sequence[float], period: int) -> Series:
    """標本標準偏差 (移動窓)。"""
    _check_period(period)
    out: Series = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        mean = sum(window) / period
        var = sum((v - mean) ** 2 for v in window) / period
        out[i] = math.sqrt(var)
    return out


def bollinger(values: Sequence[float], period: int = 20, mult: float = 2.0):
    """ボリンジャーバンド。(上限, 中心, 下限) を返す。"""
    mid = sma(values, period)
    sd = stdev(values, period)
    upper: Series = [None] * len(values)
    lower: Series = [None] * len(values)
    for i in range(len(values)):
        if mid[i] is not None and sd[i] is not None:
            upper[i] = mid[i] + mult * sd[i]
            lower[i] = mid[i] - mult * sd[i]
    return upper, mid, lower


def macd(values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD。(macd線, シグナル線, ヒストグラム) を返す。"""
    fast_line = ema(values, fast)
    slow_line = ema(values, slow)
    macd_line: Series = [None] * len(values)
    for i in range(len(values)):
        if fast_line[i] is not None and slow_line[i] is not None:
            macd_line[i] = fast_line[i] - slow_line[i]

    valid = [v for v in macd_line if v is not None]
    signal_vals = ema(valid, signal)
    signal_line: Series = [None] * len(values)
    offset = len(values) - len(valid)
    for i, v in enumerate(signal_vals):
        signal_line[offset + i] = v

    hist: Series = [None] * len(values)
    for i in range(len(values)):
        if macd_line[i] is not None and signal_line[i] is not None:
            hist[i] = macd_line[i] - signal_line[i]
    return macd_line, signal_line, hist


def highest(values: Sequence[float], period: int) -> Series:
    """直近 period 本の最高値 (現在足を含む)。"""
    _check_period(period)
    out: Series = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = max(values[i - period + 1 : i + 1])
    return out


def lowest(values: Sequence[float], period: int) -> Series:
    _check_period(period)
    out: Series = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = min(values[i - period + 1 : i + 1])
    return out


def crossed_up(series: Series, other: Series, i: int) -> bool:
    """i 本目で series が other を下から上に抜けたか。"""
    if i < 1:
        return False
    a0, a1 = series[i - 1], series[i]
    b0, b1 = other[i - 1], other[i]
    if None in (a0, a1, b0, b1):
        return False
    return a0 <= b0 and a1 > b1


def crossed_down(series: Series, other: Series, i: int) -> bool:
    if i < 1:
        return False
    a0, a1 = series[i - 1], series[i]
    b0, b1 = other[i - 1], other[i]
    if None in (a0, a1, b0, b1):
        return False
    return a0 >= b0 and a1 < b1
