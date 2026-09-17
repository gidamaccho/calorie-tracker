"""移動平均クロス + トレンドフィルタ。

短期MAが長期MAを上抜けたら買い、下抜けたら売り。
長期トレンドフィルタ (trend_period) を入れて、より上位の流れに逆らう
エントリーを弾く。ダマシを減らすのが目的。
"""

from __future__ import annotations

from typing import Optional

from ..indicators import atr, crossed_down, crossed_up, sma
from ..models import Instrument, Position, Signal, SignalType
from .base import Strategy


class SmaCrossStrategy(Strategy):
    name = "sma_cross"

    def __init__(
        self,
        instrument: Instrument,
        fast: int = 20,
        slow: int = 50,
        trend_period: int = 200,
        atr_period: int = 14,
        atr_stop_mult: float = 2.0,
        atr_tp_mult: float = 3.0,
        use_trend_filter: bool = True,
    ) -> None:
        super().__init__(instrument)
        if fast >= slow:
            raise ValueError(f"fast({fast}) は slow({slow}) より小さくすること")
        self.fast = fast
        self.slow = slow
        self.trend_period = trend_period
        self.atr_period = atr_period
        self.atr_stop_mult = atr_stop_mult
        self.atr_tp_mult = atr_tp_mult
        self.use_trend_filter = use_trend_filter

    @property
    def warmup(self) -> int:
        base = self.trend_period if self.use_trend_filter else self.slow
        return max(base, self.atr_period) + 2

    def on_candle(self, position: Optional[Position]) -> Signal:
        if not self.ready:
            return Signal.none()

        closes = self.closes
        i = len(closes) - 1
        fast_line = sma(closes, self.fast)
        slow_line = sma(closes, self.slow)
        atr_line = atr(self.candles, self.atr_period)
        cur_atr = atr_line[i]
        price = closes[i]

        up = crossed_up(fast_line, slow_line, i)
        down = crossed_down(fast_line, slow_line, i)

        # 建玉があるときは、逆向きのクロスで手仕舞い
        if position is not None:
            if position.side.name == "BUY" and down:
                return Signal(SignalType.EXIT, reason="MAデッドクロス")
            if position.side.name == "SELL" and up:
                return Signal(SignalType.EXIT, reason="MAゴールデンクロス")
            return Signal.none()

        if cur_atr is None or cur_atr <= 0:
            return Signal.none()

        trend_ok_long = True
        trend_ok_short = True
        if self.use_trend_filter:
            trend = sma(closes, self.trend_period)[i]
            if trend is None:
                return Signal.none()
            trend_ok_long = price > trend
            trend_ok_short = price < trend

        if up and trend_ok_long:
            return Signal(
                SignalType.ENTRY_LONG,
                reason=f"GC fast={self.fast} slow={self.slow}",
                stop_price=price - self.atr_stop_mult * cur_atr,
                take_profit_price=price + self.atr_tp_mult * cur_atr,
            )
        if down and trend_ok_short:
            return Signal(
                SignalType.ENTRY_SHORT,
                reason=f"DC fast={self.fast} slow={self.slow}",
                stop_price=price + self.atr_stop_mult * cur_atr,
                take_profit_price=price - self.atr_tp_mult * cur_atr,
            )
        return Signal.none()

    def describe(self) -> str:
        filt = f" trend={self.trend_period}" if self.use_trend_filter else ""
        return f"SMAクロス fast={self.fast} slow={self.slow}{filt}"
