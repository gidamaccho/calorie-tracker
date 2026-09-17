"""戦略の基底クラス。

エンジンは「確定した足」だけを on_candle に渡す。戦略は自分が持っている
履歴だけを見て判断すること。未来の足を参照する実装を書くとバックテストの
成績だけが良くなり、実運用で必ず負ける。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ..models import Candle, Instrument, Position, Signal


class Strategy(ABC):
    """すべての戦略の基底。

    必要な履歴本数を warmup で申告する。エンジンは warmup 本に満たない間は
    シグナルを無視するので、指標が None の期間に誤発注しない。
    """

    name = "base"

    def __init__(self, instrument: Instrument) -> None:
        self.instrument = instrument
        self.candles: List[Candle] = []

    @property
    @abstractmethod
    def warmup(self) -> int:
        """判断に必要な最低足数。"""

    def feed(self, candle: Candle) -> None:
        """履歴に足を追加する。エンジンが on_candle の前に呼ぶ。"""
        self.candles.append(candle)
        # 履歴が無限に伸びないよう、必要分の余裕だけ残して切る
        limit = max(self.warmup * 4, 500)
        if len(self.candles) > limit * 2:
            self.candles = self.candles[-limit:]

    @property
    def ready(self) -> bool:
        return len(self.candles) >= self.warmup

    @property
    def closes(self) -> List[float]:
        return [c.close for c in self.candles]

    @abstractmethod
    def on_candle(self, position: Optional[Position]) -> Signal:
        """足の確定ごとに呼ばれる。

        position: 現在の建玉 (なければ None)。建玉がある間は EXIT を返せる。
        """

    def describe(self) -> str:
        return self.name
