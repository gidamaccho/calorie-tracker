"""RSI 逆張り (レンジ相場向け)。

RSI が売られすぎ圏から戻ってきたら買い、買われすぎ圏から戻ってきたら売る。
「閾値を割った瞬間」ではなく「割ってから戻った時」に入るのがポイントで、
下落が続く相場でナイフを掴み続けるのを避ける。
"""

from __future__ import annotations

from typing import Optional

from ..indicators import atr, rsi, sma
from ..models import Instrument, Position, Signal, SignalType
from .base import Strategy


class RsiReversionStrategy(Strategy):
    name = "rsi_reversion"

    def __init__(
        self,
        instrument: Instrument,
        rsi_period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        exit_level: float = 50.0,
        atr_period: int = 14,
        atr_stop_mult: float = 1.5,
        atr_tp_mult: float = 2.0,
        trend_period: int = 0,
    ) -> None:
        super().__init__(instrument)
        if not 0 < oversold < overbought < 100:
            raise ValueError("oversold < overbought かつ 0-100 の範囲で指定すること")
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.exit_level = exit_level
        self.atr_period = atr_period
        self.atr_stop_mult = atr_stop_mult
        self.atr_tp_mult = atr_tp_mult
        self.trend_period = trend_period

    @property
    def warmup(self) -> int:
        return max(self.rsi_period, self.atr_period, self.trend_period) + 3

    def on_candle(self, position: Optional[Position]) -> Signal:
        if not self.ready:
            return Signal.none()

        closes = self.closes
        i = len(closes) - 1
        rsi_line = rsi(closes, self.rsi_period)
        cur, prev = rsi_line[i], rsi_line[i - 1]
        if cur is None or prev is None:
            return Signal.none()

        if position is not None:
            # 中立圏に戻ったら利益確定 (逆張りは引っ張らない)
            if position.side.name == "BUY" and cur >= self.exit_level:
                return Signal(SignalType.EXIT, reason=f"RSI {cur:.1f} が中立圏に回復")
            if position.side.name == "SELL" and cur <= self.exit_level:
                return Signal(SignalType.EXIT, reason=f"RSI {cur:.1f} が中立圏に低下")
            return Signal.none()

        cur_atr = atr(self.candles, self.atr_period)[i]
        if cur_atr is None or cur_atr <= 0:
            return Signal.none()
        price = closes[i]

        if self.trend_period:
            trend = sma(closes, self.trend_period)[i]
            if trend is None:
                return Signal.none()
        else:
            trend = None

        # 売られすぎ圏から上抜け = 買い
        if prev <= self.oversold < cur:
            if trend is not None and price < trend:
                return Signal.none()
            return Signal(
                SignalType.ENTRY_LONG,
                reason=f"RSI {prev:.1f}→{cur:.1f} 売られすぎから反転",
                stop_price=price - self.atr_stop_mult * cur_atr,
                take_profit_price=price + self.atr_tp_mult * cur_atr,
            )
        # 買われすぎ圏から下抜け = 売り
        if prev >= self.overbought > cur:
            if trend is not None and price > trend:
                return Signal.none()
            return Signal(
                SignalType.ENTRY_SHORT,
                reason=f"RSI {prev:.1f}→{cur:.1f} 買われすぎから反転",
                stop_price=price + self.atr_stop_mult * cur_atr,
                take_profit_price=price - self.atr_tp_mult * cur_atr,
            )
        return Signal.none()

    def describe(self) -> str:
        return (
            f"RSI逆張り period={self.rsi_period} "
            f"{self.oversold:.0f}/{self.overbought:.0f}"
        )
