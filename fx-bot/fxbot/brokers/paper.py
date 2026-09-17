"""ペーパートレード用ブローカー。

実弾を一切使わずにエンジン全体を動かすための実装。バックテストにも使う。
現実に寄せるため次を模擬する:
  - スプレッド: 買いは Ask、売りは Bid で約定
  - スリッページ: 成行約定の不利方向へのずれ
  - 損切り/利確の足内判定: 高値・安値がレベルに触れたら約定
  - 手数料・スワップ (簡易)

意図的に悲観側へ倒してある。ここで勝てない戦略は実弾でも勝てない。
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, List, Optional

from ..models import Candle, Instrument, Order, Position, Side, Tick, Trade
from ..pricesource import PriceSource
from .base import Broker, BrokerError


class PaperBroker(Broker):
    is_live = False

    def __init__(
        self,
        starting_balance: float = 1_000_000.0,
        spread_pips: float = 0.4,
        slippage_pips: float = 0.2,
        commission_per_10k: float = 0.0,
        swap_per_10k_per_day: float = 0.0,
        jpy_rate_provider: Optional[Callable[[], float]] = None,
        price_source: Optional[PriceSource] = None,
    ) -> None:
        self.balance = starting_balance
        self.starting_balance = starting_balance
        self.spread_pips = spread_pips
        self.slippage_pips = slippage_pips
        self.commission_per_10k = commission_per_10k
        self.swap_per_10k_per_day = swap_per_10k_per_day
        self._jpy_rate_provider = jpy_rate_provider
        # リアルタイム稼働時の価格供給源。バックテストでは使わない
        # (バックテスト側が set_market で1本ずつ足を差し込むため)。
        self.price_source = price_source

        self.positions: List[Position] = []
        self.trades: List[Trade] = []
        # 損切り・利確で決済され、まだエンジンが回収していない取引
        self._pending_closed: List[Trade] = []
        self.equity_curve: List[tuple] = []  # (datetime, equity)
        self._current: Optional[Candle] = None
        self._instrument: Optional[Instrument] = None
        self._connected = False

    # ------------------------------------------------------------------
    # Broker インターフェース
    # ------------------------------------------------------------------
    def connect(self) -> None:
        if self.price_source is not None:
            self.price_source.connect()
        self._connected = True

    def disconnect(self) -> None:
        if self.price_source is not None:
            self.price_source.disconnect()
        self._connected = False

    @property
    def jpy_rate(self) -> float:
        return self._jpy_rate_provider() if self._jpy_rate_provider else 1.0

    def set_market(self, instrument: Instrument, candle: Candle) -> None:
        """現在の足を差し込む。バックテスト側が1本ずつ進める。"""
        self._instrument = instrument
        self._current = candle

    def get_tick(self, instrument: Instrument) -> Tick:
        if self.price_source is not None:
            tick = self.price_source.get_tick(instrument)
            # 現在値を更新し、そのうえで損切り・利確の到達を確認する。
            # ここを飛ばすと、リアルタイム稼働時に建玉が決済されないまま残る。
            self.set_market(
                instrument,
                Candle(tick.time, tick.mid, tick.mid, tick.mid, tick.mid),
            )
            self.check_stops(instrument, tick.mid, tick.time)
            return tick

        if self._current is None:
            raise BrokerError(
                "価格の供給源が無い。バックテストでは set_market を、"
                "リアルタイム稼働では price_source を指定すること"
            )
        half = instrument.pips_to_price(self.spread_pips) / 2.0
        mid = self._current.close
        return Tick(time=self._current.time, bid=mid - half, ask=mid + half)

    def get_equity(self) -> float:
        unrealized = 0.0
        if self._current is not None:
            price = self._current.close
            unrealized = sum(p.unrealized_pnl(price, self.jpy_rate) for p in self.positions)
        return self.balance + unrealized

    def get_positions(self, instrument: Optional[Instrument] = None) -> List[Position]:
        if instrument is None:
            return list(self.positions)
        return [p for p in self.positions if p.instrument.symbol == instrument.symbol]

    def poll_closed_trades(self) -> List[Trade]:
        drained, self._pending_closed = self._pending_closed, []
        return drained

    def place_order(self, order: Order) -> Position:
        if self._current is None:
            raise BrokerError("市場データが未設定")
        if order.units <= 0:
            raise BrokerError(f"数量が不正: {order.units}")

        fill = self._fill_price(order.instrument, order.side, self._current.close)
        position = Position(
            instrument=order.instrument,
            side=order.side,
            units=order.units,
            entry_price=fill,
            entry_time=self._current.time,
            stop_price=order.stop_price,
            take_profit_price=order.take_profit_price,
            reason=order.reason,
        )
        self.positions.append(position)
        return position

    def close_position(self, position: Position, reason: str = "") -> Trade:
        if self._current is None:
            raise BrokerError("市場データが未設定")
        exit_price = self._fill_price(
            position.instrument, position.side.opposite, self._current.close
        )
        return self._settle(position, exit_price, self._current.time, reason)

    # ------------------------------------------------------------------
    # バックテスト用の内部処理
    # ------------------------------------------------------------------
    def process_candle(self, candle: Candle, instrument: Instrument) -> List[Trade]:
        """足の値動きで損切り・利確に掛かった建玉を決済する。

        1本の中で損切りと利確の両方に触れた場合は、必ず損切りが先に約定した
        ものとして扱う。足データからは順序が分からないので、成績を甘く
        見積もらないための保守的な仮定。
        """
        self.set_market(instrument, candle)
        closed: List[Trade] = []

        for position in list(self.positions):
            stop = position.stop_price
            tp = position.take_profit_price
            hit_stop = stop is not None and (
                candle.low <= stop if position.side is Side.BUY else candle.high >= stop
            )
            hit_tp = tp is not None and (
                candle.high >= tp if position.side is Side.BUY else candle.low <= tp
            )

            if hit_stop:
                # 損切りは不利方向のスリッページを乗せる (窓開けを想定)
                slip = position.instrument.pips_to_price(self.slippage_pips)
                price = stop - slip * position.side.sign
                closed.append(self._settle(position, price, candle.time, "損切り"))
            elif hit_tp:
                closed.append(self._settle(position, tp, candle.time, "利確"))

        self.equity_curve.append((candle.time, self.get_equity()))
        return closed

    def check_stops(
        self, instrument: Instrument, price: float, when: datetime
    ) -> List[Trade]:
        """現在値が損切り・利確に到達した建玉を決済する (ティック単位)。"""
        closed: List[Trade] = []
        for position in list(self.positions):
            if position.instrument.symbol != instrument.symbol:
                continue
            stop, tp = position.stop_price, position.take_profit_price
            if stop is not None and (
                price <= stop if position.side is Side.BUY else price >= stop
            ):
                slip = position.instrument.pips_to_price(self.slippage_pips)
                closed.append(
                    self._settle(position, stop - slip * position.side.sign, when, "損切り")
                )
            elif tp is not None and (
                price >= tp if position.side is Side.BUY else price <= tp
            ):
                closed.append(self._settle(position, tp, when, "利確"))
        self._pending_closed.extend(closed)
        return closed

    def _settle(
        self, position: Position, exit_price: float, when: datetime, reason: str
    ) -> Trade:
        if position not in self.positions:
            raise BrokerError("既に決済済みの建玉")
        rate = 1.0 if position.instrument.quote_is_jpy else self.jpy_rate
        gross = (exit_price - position.entry_price) * position.side.sign * position.units * rate
        # 手数料は往復ぶん (建玉時と決済時) をここでまとめて計上する。
        cost = self._commission(position.units) * 2 + self._swap(position, when)
        pnl = gross - cost

        self.balance += pnl
        self.positions.remove(position)

        trade = Trade(
            instrument=position.instrument,
            side=position.side,
            units=position.units,
            entry_price=position.entry_price,
            exit_price=exit_price,
            entry_time=position.entry_time,
            exit_time=when,
            pnl=pnl,
            exit_reason=reason,
            entry_reason=position.reason,
        )
        self.trades.append(trade)
        return trade

    def _fill_price(self, instrument: Instrument, side: Side, mid: float) -> float:
        """成行の約定価格。常に不利な側へずらす。"""
        half_spread = instrument.pips_to_price(self.spread_pips) / 2.0
        slip = instrument.pips_to_price(self.slippage_pips)
        return mid + (half_spread + slip) * side.sign

    def _commission(self, units: int) -> float:
        return self.commission_per_10k * (units / 10_000.0)

    def _swap(self, position: Position, when: datetime) -> float:
        if self.swap_per_10k_per_day == 0:
            return 0.0
        days = max((when - position.entry_time).total_seconds() / 86400.0, 0.0)
        return self.swap_per_10k_per_day * (position.units / 10_000.0) * days
