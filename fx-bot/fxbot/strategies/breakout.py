"""ドンチャン・ブレイクアウト (順張り)。

直近 N 本の高値を上抜けたら買い、安値を下抜けたら売り。
決済は反対側の短い期間のチャネル (exit_period) に触れたら。
いわゆるタートル流の簡易版。トレンドが出る相場に強く、レンジで削られる。
"""

from __future__ import annotations

from typing import Optional

from ..indicators import atr, highest, lowest
from ..models import Instrument, Position, Side, Signal, SignalType
from .base import Strategy


class BreakoutStrategy(Strategy):
    name = "breakout"

    def __init__(
        self,
        instrument: Instrument,
        entry_period: int = 20,
        exit_period: int = 10,
        atr_period: int = 14,
        atr_stop_mult: float = 2.0,
        atr_tp_mult: float = 0.0,  # 0 = 利確目標なし (トレンドに任せる)
    ) -> None:
        super().__init__(instrument)
        self.entry_period = entry_period
        self.exit_period = exit_period
        self.atr_period = atr_period
        self.atr_stop_mult = atr_stop_mult
        self.atr_tp_mult = atr_tp_mult

    @property
    def warmup(self) -> int:
        return max(self.entry_period, self.exit_period, self.atr_period) + 2

    def on_candle(self, position: Optional[Position]) -> Signal:
        if not self.ready:
            return Signal.none()

        i = len(self.candles) - 1
        highs = [c.high for c in self.candles]
        lows = [c.low for c in self.candles]
        price = self.candles[i].close

        if position is not None:
            # 直前の足までのチャネルで判定する (現在足自身を含めない)
            exit_low = lowest(lows[:-1], self.exit_period)[-1]
            exit_high = highest(highs[:-1], self.exit_period)[-1]
            if position.side is Side.BUY and exit_low is not None and price < exit_low:
                return Signal(SignalType.EXIT, reason=f"{self.exit_period}本安値割れ")
            if position.side is Side.SELL and exit_high is not None and price > exit_high:
                return Signal(SignalType.EXIT, reason=f"{self.exit_period}本高値超え")
            return Signal.none()

        cur_atr = atr(self.candles, self.atr_period)[i]
        if cur_atr is None or cur_atr <= 0:
            return Signal.none()

        # 現在足を除いた過去 entry_period 本のレンジを基準にする
        prior_high = highest(highs[:-1], self.entry_period)[-1]
        prior_low = lowest(lows[:-1], self.entry_period)[-1]
        if prior_high is None or prior_low is None:
            return Signal.none()

        if price > prior_high:
            return Signal(
                SignalType.ENTRY_LONG,
                reason=f"{self.entry_period}本高値 {prior_high:.3f} 上抜け",
                stop_price=price - self.atr_stop_mult * cur_atr,
                take_profit_price=(
                    price + self.atr_tp_mult * cur_atr if self.atr_tp_mult else None
                ),
            )
        if price < prior_low:
            return Signal(
                SignalType.ENTRY_SHORT,
                reason=f"{self.entry_period}本安値 {prior_low:.3f} 下抜け",
                stop_price=price + self.atr_stop_mult * cur_atr,
                take_profit_price=(
                    price - self.atr_tp_mult * cur_atr if self.atr_tp_mult else None
                ),
            )
        return Signal.none()

    def describe(self) -> str:
        return f"ブレイクアウト entry={self.entry_period} exit={self.exit_period}"
