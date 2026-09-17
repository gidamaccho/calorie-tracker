"""ライブ / ペーパー稼働用のエンジン。

バックテストと同じ判断ロジックを、実時間のループで回す。
安全のために次を必ず守る:
  - 未確定足では判断しない (足の確定を待つ)
  - ブローカーのエラーは握りつぶさず、連続したら停止する
  - Ctrl+C / SIGTERM で建玉の扱いを選んでから終了する
  - リスク管理が停止を指示したら、新規建玉を止める (既存建玉の決済は続ける)
"""

from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from .brokers.base import Broker, BrokerError
from .journal import Journal
from .models import Candle, Instrument, Order, Position, SignalType, utcnow
from .risk import RiskConfig, RiskManager
from .strategies.base import Strategy

log = logging.getLogger(__name__)


@dataclass
class EngineConfig:
    bar_minutes: int = 60          # 足の長さ
    poll_seconds: float = 5.0      # 価格取得の間隔
    max_consecutive_errors: int = 5
    close_positions_on_stop: bool = False  # 停止時に建玉を決済するか
    max_runtime_hours: float = 0.0         # 0 = 無制限


class TradingEngine:
    def __init__(
        self,
        broker: Broker,
        strategy: Strategy,
        instrument: Instrument,
        risk_config: Optional[RiskConfig] = None,
        engine_config: Optional[EngineConfig] = None,
        journal: Optional[Journal] = None,
        warmup_candles: Optional[List[Candle]] = None,
    ) -> None:
        self.broker = broker
        self.strategy = strategy
        self.instrument = instrument
        self.engine_config = engine_config or EngineConfig()
        self.journal = journal or Journal(enabled=False)

        self._running = False
        self._errors = 0
        self._builder = _CandleBuilder(self.engine_config.bar_minutes)
        self.risk: Optional[RiskManager] = None
        self._risk_config = risk_config or RiskConfig()

        # 過去の足を流し込んで指標を温めておく。
        # これをしないと、起動直後の warmup 本分だけ取引できない。
        if warmup_candles:
            for candle in warmup_candles:
                self.strategy.feed(candle)
            log.info("過去 %d 本で指標を初期化した", len(warmup_candles))

    # ------------------------------------------------------------------
    def run(self) -> None:
        if self.broker.is_live:
            log.warning("=" * 60)
            log.warning("実弾モードで起動する。資金が実際に動く。")
            log.warning("=" * 60)

        self.broker.connect()
        equity = self.broker.get_equity()
        self.risk = RiskManager(self._risk_config, equity)
        self.journal.event("engine_start", equity=equity,
                           strategy=self.strategy.describe(),
                           symbol=self.instrument.symbol,
                           live=self.broker.is_live)
        log.info(
            "開始: %s / %s / 有効証拠金 %s 円",
            self.strategy.describe(),
            self.instrument.symbol,
            f"{equity:,.0f}",
        )

        self._running = True
        self._install_signal_handlers()
        started = utcnow()
        deadline = (
            started + timedelta(hours=self.engine_config.max_runtime_hours)
            if self.engine_config.max_runtime_hours
            else None
        )

        try:
            while self._running:
                if deadline and utcnow() >= deadline:
                    log.info("最大稼働時間に到達したので停止する")
                    break
                self._tick()
                time.sleep(self.engine_config.poll_seconds)
        except KeyboardInterrupt:
            log.info("Ctrl+C を受け取った")
        finally:
            self._shutdown()

    def _tick(self) -> None:
        try:
            tick = self.broker.get_tick(self.instrument)
            self._errors = 0
        except BrokerError as exc:
            self._errors += 1
            log.error("価格取得に失敗 (%d/%d): %s",
                      self._errors, self.engine_config.max_consecutive_errors, exc)
            self.journal.event("error", stage="get_tick", detail=str(exc))
            if self._errors >= self.engine_config.max_consecutive_errors:
                log.critical("エラーが連続したので停止する")
                self._running = False
            return

        # 損切り・利確で決済された取引を回収する。
        # 足の確定を待たずに毎ティック行う (決済は足の途中で起きるため)。
        self._collect_broker_closes()

        closed = self._builder.update(tick.time, tick.mid)
        if closed is None:
            return  # 足がまだ確定していない

        log.debug("足確定 %s C=%.3f", closed.time, closed.close)
        try:
            self._on_candle_closed(closed, tick)
        except BrokerError as exc:
            log.error("発注処理に失敗: %s", exc)
            self.journal.event("error", stage="on_candle", detail=str(exc))
            self._errors += 1
            if self._errors >= self.engine_config.max_consecutive_errors:
                log.critical("エラーが連続したので停止する")
                self._running = False

    def _collect_broker_closes(self) -> None:
        assert self.risk is not None
        for trade in self.broker.poll_closed_trades():
            self.risk.on_trade_closed(trade.pnl)
            self.journal.record_trade(trade)
            log.info(
                "決済(業者側): %s %s 円 (%s)",
                trade.instrument.symbol,
                f"{trade.pnl:+,.0f}",
                trade.exit_reason,
            )
            if self.risk.state.halted:
                log.warning("リスク管理により取引を停止: %s", self.risk.state.halt_reason)

    def _on_candle_closed(self, candle: Candle, tick) -> None:
        assert self.risk is not None
        equity = self.broker.get_equity()
        self.risk.on_new_bar(candle.time, equity)

        self.strategy.feed(candle)
        positions = self.broker.get_positions(self.instrument)
        position: Optional[Position] = positions[0] if positions else None

        if position is not None and self.risk.update_trailing_stop(position, candle.close):
            self.broker.modify_position(position)
            self.journal.event("trailing_stop_moved",
                               symbol=self.instrument.symbol,
                               new_stop=position.stop_price)

        signal = self.strategy.on_candle(position)

        if signal.type is SignalType.EXIT and position is not None:
            trade = self.broker.close_position(position, signal.reason or "戦略シグナル")
            self.risk.on_trade_closed(trade.pnl)
            self.journal.record_trade(trade)
            log.info(
                "決済: %s %s 円 (%s)",
                self.instrument.symbol,
                f"{trade.pnl:+,.0f}",
                trade.exit_reason,
            )
            return

        if signal.is_entry and position is None:
            side = signal.side
            assert side is not None
            spread_pips = self.instrument.price_to_pips(tick.spread)
            decision = self.risk.evaluate_entry(
                instrument=self.instrument,
                side=side,
                entry_price=candle.close,
                stop_price=signal.stop_price,
                equity=equity,
                open_positions=self.broker.get_positions(),
                now=candle.time,
                spread_pips=spread_pips,
            )
            if not decision:
                log.info("見送り: %s", decision.reason)
                self.journal.event("entry_blocked", reason=decision.reason,
                                   signal=signal.reason)
                return

            stop = signal.stop_price
            if stop is None:
                offset = self.instrument.pips_to_price(self._risk_config.default_stop_pips)
                stop = candle.close - offset * side.sign

            order = Order(
                instrument=self.instrument,
                side=side,
                units=decision.units,
                stop_price=stop,
                take_profit_price=signal.take_profit_price,
                reason=signal.reason,
            )
            opened = self.broker.place_order(order)
            self.journal.record_position(opened)
            log.info("建玉: %s %s %s units @ %.3f (SL %.3f) %s",
                     self.instrument.symbol, side.value, opened.units,
                     opened.entry_price, stop, signal.reason)

    # ------------------------------------------------------------------
    def stop(self) -> None:
        self._running = False

    def _install_signal_handlers(self) -> None:
        def handler(signum, _frame):
            log.info("シグナル %s を受信。停止処理へ移る", signum)
            self._running = False

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):  # メインスレッド以外では設定できない
                pass

    def _shutdown(self) -> None:
        try:
            positions = self.broker.get_positions(self.instrument)
            if positions:
                if self.engine_config.close_positions_on_stop:
                    log.warning("停止処理: 建玉 %d 件を決済する", len(positions))
                    for trade in self.broker.close_all("エンジン停止"):
                        self.journal.record_trade(trade)
                else:
                    log.warning(
                        "停止するが建玉 %d 件が残っている。"
                        "損切り注文は業者側に残るが、監視は止まる。"
                        "取引画面で必ず確認すること",
                        len(positions),
                    )
                    self.journal.event("shutdown_with_open_positions",
                                       count=len(positions))
        except BrokerError as exc:
            log.error("停止処理中のエラー: %s", exc)
        finally:
            self.journal.event("engine_stop")
            self.broker.disconnect()
            log.info("停止した")


class _CandleBuilder:
    """ティックから一定時間の足を組み立てる。

    足は「次の足の時間に入った瞬間」に確定する。確定前の足は返さない
    ので、戦略が未完成の足で判断することがない。
    """

    def __init__(self, bar_minutes: int) -> None:
        if bar_minutes < 1:
            raise ValueError("bar_minutes は1以上")
        self.bar_minutes = bar_minutes
        self._start: Optional[datetime] = None
        self._o = self._h = self._l = self._c = 0.0
        self._ticks = 0

    def _bucket(self, when: datetime) -> datetime:
        when = when.astimezone(timezone.utc)
        minutes = (when.hour * 60 + when.minute) // self.bar_minutes * self.bar_minutes
        return when.replace(
            hour=minutes // 60, minute=minutes % 60, second=0, microsecond=0
        )

    def update(self, when: datetime, price: float) -> Optional[Candle]:
        bucket = self._bucket(when)

        if self._start is None:
            self._start = bucket
            self._o = self._h = self._l = self._c = price
            self._ticks = 1
            return None

        if bucket == self._start:
            self._h = max(self._h, price)
            self._l = min(self._l, price)
            self._c = price
            self._ticks += 1
            return None

        finished = Candle(
            time=self._start, open=self._o, high=self._h,
            low=self._l, close=self._c, volume=self._ticks,
        )
        self._start = bucket
        self._o = self._h = self._l = self._c = price
        self._ticks = 1
        return finished
