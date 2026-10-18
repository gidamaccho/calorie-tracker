"""ライブ(デモ口座)自動売買ループ。"""
import logging
import os
import time
from datetime import datetime, timezone

from .config import Config
from .indicators import atr
from .risk import DailyLossGuard, calc_lots, pip_size
from .strategies import Strategy

log = logging.getLogger("fxbot.live")

ALLOW_LIVE_ENV = "FXBOT_ALLOW_LIVE"


def check_account_allowed(broker, cfg: Config) -> None:
    """リアル口座での誤稼働を防ぐ。設定と環境変数の両方が揃ったときだけ許可。"""
    if broker.is_demo():
        return
    if cfg.live.allow_live_account and os.environ.get(ALLOW_LIVE_ENV) == "yes":
        log.warning("リアル口座で稼働します。損失が出る可能性があります。")
        return
    raise RuntimeError(
        "接続先がリアル口座のため停止しました。デモ口座で使ってください。"
        f"(どうしてもリアルで動かす場合は live.allow_live_account: true と環境変数 {ALLOW_LIVE_ENV}=yes が必要)"
    )


class Trader:
    def __init__(self, broker, strategy: Strategy, cfg: Config):
        self.broker = broker
        self.strategy = strategy
        self.cfg = cfg
        self.guard = DailyLossGuard(cfg.risk.max_daily_loss_pct)
        self.last_bar_time = None
        self.spec = None

    def start(self) -> None:
        check_account_allowed(self.broker, self.cfg)
        self.spec = self.broker.symbol_spec(self.cfg.symbol)
        log.info(self.broker.account_summary())
        log.info("戦略: %s / %s %s%s", self.strategy, self.cfg.symbol, self.cfg.timeframe,
                 "(dry run: 発注しません)" if self.cfg.live.dry_run else "")

    def step(self) -> None:
        """新しい足が確定していればシグナルを判定し、必要なら発注する。"""
        cfg, live, risk = self.cfg, self.cfg.live, self.cfg.risk
        df = self.broker.closed_bars(cfg.symbol, cfg.timeframe, max(live.history_bars, self.strategy.min_bars + risk.atr_period))
        bar_time = df.index[-1]
        if bar_time == self.last_bar_time:
            return
        first = self.last_bar_time is None
        self.last_bar_time = bar_time
        if first:
            # 起動直後は「すでに出ていた古いシグナル」で入らないよう、次の足から判定する
            log.info("最新の確定足 %s から監視を開始", bar_time)
            return
        if len(df) < self.strategy.min_bars:
            log.warning("足の本数が不足しています(%d < %d)", len(df), self.strategy.min_bars)
            return

        signal = int(self.strategy.signals(df).iloc[-1])
        pos = self.broker.position(cfg.symbol, live.magic)
        log.info("足確定 %s close=%s シグナル=%s ポジション=%s", bar_time, df["close"].iloc[-1],
                 {1: "買い", -1: "売り", 0: "なし"}[signal], pos and ("買い" if pos.direction == 1 else "売り"))
        if signal == 0 or (pos and pos.direction == signal):
            return

        if pos:
            log.info("反対シグナルのため決済: ticket=%s", pos.ticket)
            if not live.dry_run:
                self.broker.close(cfg.symbol, pos, live.magic, live.deviation_points)

        equity = self.broker.equity()
        if not self.guard.can_open(datetime.now(timezone.utc).date(), equity):
            log.warning("本日の損失上限 %.1f%% に達したため新規エントリーを見送り", risk.max_daily_loss_pct)
            return

        bid, ask = self.broker.bid_ask(cfg.symbol)
        spread_pips = (ask - bid) / pip_size(cfg.symbol)
        if spread_pips > risk.max_spread_pips:
            log.warning("スプレッド %.1f pips が上限 %.1f を超えたため見送り", spread_pips, risk.max_spread_pips)
            return

        a = float(atr(df, risk.atr_period).iloc[-1])
        sl_dist, tp_dist = a * risk.sl_atr_mult, a * risk.tp_atr_mult
        spec = self.spec
        lots = calc_lots(equity, risk.risk_per_trade_pct, sl_dist, spec.value_per_price_per_lot,
                         spec.volume_min, spec.volume_step, spec.volume_max)
        if lots <= 0:
            log.warning("資金に対して損切り幅が大きく、最小ロットでもリスク上限を超えるため見送り")
            return

        entry = ask if signal == 1 else bid
        sl = round(entry - signal * sl_dist, spec.digits)
        tp = round(entry + signal * tp_dist, spec.digits)
        log.info("新規%s %.2f ロット 価格≈%s SL=%s TP=%s", "買い" if signal == 1 else "売り", lots, entry, sl, tp)
        if not live.dry_run:
            self.broker.open(cfg.symbol, signal, lots, sl, tp, live.magic, live.deviation_points)

    def run(self) -> None:
        self.start()
        errors = 0
        while True:
            try:
                self.step()
                errors = 0
            except KeyboardInterrupt:
                raise
            except Exception:
                errors += 1
                log.exception("エラーが発生しました(連続 %d 回)", errors)
                if errors >= 10:
                    log.error("エラーが続いたため停止します")
                    raise
            time.sleep(self.cfg.live.poll_seconds * min(errors + 1, 6))
