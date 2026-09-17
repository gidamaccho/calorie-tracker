"""ペーパートレード用の価格供給源。

PaperBroker は約定を模擬するだけで、価格そのものは持たない。
リアルタイムで動かすときは、どこかから現在値を貰う必要がある。

  LiveQuoteSource : 実ブローカー (OANDA等) の気配値を使う。約定だけ模擬する。
                    → 実弾に一番近い形での検証ができる。
  ReplayQuoteSource: 保存済みの足を順に流す。オフラインで配管の確認ができる。
"""

from __future__ import annotations

import logging
from typing import Iterator, Optional, Protocol, Sequence, runtime_checkable

from .models import Candle, Instrument, Tick

log = logging.getLogger(__name__)


@runtime_checkable
class PriceSource(Protocol):
    """現在値を供給するもの。"""

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def get_tick(self, instrument: Instrument) -> Tick: ...


class LiveQuoteSource:
    """実ブローカーの気配値を使う。発注は一切行わない。

    これを PaperBroker に渡すと「本物の価格・偽の約定」になり、
    実弾投入前の最終確認として最も現実に近い検証ができる。
    """

    def __init__(self, broker) -> None:
        self.broker = broker

    def connect(self) -> None:
        self.broker.connect()
        log.info("気配値の取得元: %s (発注はしない)", type(self.broker).__name__)

    def disconnect(self) -> None:
        self.broker.disconnect()

    def get_tick(self, instrument: Instrument) -> Tick:
        return self.broker.get_tick(instrument)


class ReplayQuoteSource:
    """保存済みの足を順に再生する。

    1本の足につき始値→高値→安値→終値の順に4ティックを出す。
    これでエンジン側の足組み立てが元の足をほぼ再現する。

    値動きの順序は実際には分からないので、ここでの成績は参考値。
    正確な検証には `backtest` コマンドを使うこと。
    """

    def __init__(self, candles: Sequence[Candle], spread_pips: float = 0.4) -> None:
        if not candles:
            raise ValueError("再生する足が無い")
        self.candles = list(candles)
        self.spread_pips = spread_pips
        self._iter: Optional[Iterator[Tick]] = None
        self.exhausted = False

    def connect(self) -> None:
        self._iter = self._ticks()
        self.exhausted = False
        log.info("%d 本の足を再生する (オフライン)", len(self.candles))

    def disconnect(self) -> None:
        self._iter = None

    def _ticks(self) -> Iterator[Tick]:
        from datetime import timedelta

        for i, candle in enumerate(self.candles):
            if i + 1 < len(self.candles):
                span = self.candles[i + 1].time - candle.time
            else:
                span = timedelta(hours=1)
            step = span / 4
            for offset, price in enumerate(
                (candle.open, candle.high, candle.low, candle.close)
            ):
                yield self._make_tick(candle.time + step * offset, price)

    def _make_tick(self, when, price: float) -> Tick:
        # pip 幅はペア依存だが、再生では円建て相当の 0.01 を基準に置く
        half = self.spread_pips * 0.01 / 2.0
        return Tick(time=when, bid=price - half, ask=price + half)

    def get_tick(self, instrument: Instrument) -> Tick:
        from .brokers.base import BrokerError

        if self._iter is None:
            raise BrokerError("connect() を先に呼ぶこと")
        half = instrument.pips_to_price(self.spread_pips) / 2.0
        try:
            raw = next(self._iter)
        except StopIteration:
            self.exhausted = True
            raise BrokerError("再生する足が尽きた") from None
        mid = raw.mid
        return Tick(time=raw.time, bid=mid - half, ask=mid + half)
