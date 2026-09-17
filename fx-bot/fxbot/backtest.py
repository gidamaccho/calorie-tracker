"""バックテストと成績評価。

重要な前提 (ここを誤解すると数字を信じすぎる):
  - 判断は「確定した足の終値」で行い、約定も同じ終値ベースで行う。
    実際には終値で必ず約定できるとは限らない。
  - 1本の中で損切りと利確の両方に触れた場合、損切りが先とみなす (保守側)。
  - スプレッド・スリッページ・手数料は PaperBroker が差し引く。
  - スワップ (金利差) は簡易計算。長期保有戦略では実額と乖離する。
  - 過去データへの最適化は将来の成績を保証しない。パラメータをいじって
    数字が良くなったら、それは過学習を疑うべき場面。
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

from .brokers.paper import PaperBroker
from .models import Candle, Instrument, Order, SignalType, Trade, safe_div
from .risk import RiskConfig, RiskManager
from .strategies.base import Strategy


@dataclass
class BacktestResult:
    trades: List[Trade]
    equity_curve: List[Tuple[datetime, float]]
    starting_balance: float
    final_balance: float
    instrument: Instrument
    strategy_name: str
    bars: int
    blocked: List[Tuple[datetime, str]] = field(default_factory=list)
    halt_reason: str = ""

    # ------------------------------------------------------------------
    @property
    def net_pnl(self) -> float:
        return self.final_balance - self.starting_balance

    @property
    def return_pct(self) -> float:
        return safe_div(self.net_pnl, self.starting_balance) * 100.0

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> List[Trade]:
        return [t for t in self.trades if t.is_win]

    @property
    def losses(self) -> List[Trade]:
        return [t for t in self.trades if not t.is_win]

    @property
    def win_rate(self) -> float:
        return safe_div(len(self.wins), self.total_trades) * 100.0

    @property
    def gross_profit(self) -> float:
        return sum(t.pnl for t in self.wins)

    @property
    def gross_loss(self) -> float:
        return abs(sum(t.pnl for t in self.losses))

    @property
    def profit_factor(self) -> float:
        """総利益 / 総損失。1.0 未満なら負け越し。"""
        if self.gross_loss == 0:
            return float("inf") if self.gross_profit > 0 else 0.0
        return self.gross_profit / self.gross_loss

    @property
    def expectancy(self) -> float:
        """1トレードあたりの期待損益 (円)。"""
        return safe_div(self.net_pnl, self.total_trades)

    @property
    def avg_win(self) -> float:
        return safe_div(self.gross_profit, len(self.wins))

    @property
    def avg_loss(self) -> float:
        return safe_div(self.gross_loss, len(self.losses))

    @property
    def payoff_ratio(self) -> float:
        return safe_div(self.avg_win, self.avg_loss)

    @property
    def max_drawdown(self) -> float:
        """資産曲線の最大下落率 (0.0-1.0)。"""
        peak = -float("inf")
        worst = 0.0
        for _, equity in self.equity_curve:
            peak = max(peak, equity)
            if peak > 0:
                worst = max(worst, (peak - equity) / peak)
        return worst

    @property
    def max_drawdown_yen(self) -> float:
        peak = -float("inf")
        worst = 0.0
        for _, equity in self.equity_curve:
            peak = max(peak, equity)
            worst = max(worst, peak - equity)
        return worst

    @property
    def max_consecutive_losses(self) -> int:
        worst = run = 0
        for t in self.trades:
            run = 0 if t.is_win else run + 1
            worst = max(worst, run)
        return worst

    @property
    def sharpe(self) -> float:
        """足ごとのリターンから算出した簡易シャープレシオ (年率換算なし)。

        取引頻度が低いと意味が薄いので、参考値として扱うこと。
        """
        returns = []
        for i in range(1, len(self.equity_curve)):
            prev = self.equity_curve[i - 1][1]
            cur = self.equity_curve[i][1]
            if prev > 0:
                returns.append((cur - prev) / prev)
        if len(returns) < 2:
            return 0.0
        sd = statistics.pstdev(returns)
        if sd == 0:
            return 0.0
        return statistics.fmean(returns) / sd * math.sqrt(len(returns))

    @property
    def total_pips(self) -> float:
        return sum(t.pips for t in self.trades)

    # ------------------------------------------------------------------
    def summary(self) -> str:
        pf = self.profit_factor
        pf_text = "∞" if pf == float("inf") else f"{pf:.2f}"
        lines = [
            "=" * 62,
            f" バックテスト結果: {self.strategy_name} / {self.instrument.symbol}",
            "=" * 62,
            f"  検証足数        : {self.bars:,} 本",
            f"  初期資金        : {self.starting_balance:>14,.0f} 円",
            f"  最終資金        : {self.final_balance:>14,.0f} 円",
            f"  損益            : {self.net_pnl:>14,.0f} 円 ({self.return_pct:+.2f}%)",
            f"  獲得pips        : {self.total_pips:>14,.1f} pips",
            "-" * 62,
            f"  トレード数      : {self.total_trades:>6}  (勝 {len(self.wins)} / 負 {len(self.losses)})",
            f"  勝率            : {self.win_rate:>6.1f} %",
            f"  プロフィットファクタ: {pf_text:>6}",
            f"  期待値/トレード : {self.expectancy:>10,.0f} 円",
            f"  平均利益        : {self.avg_win:>10,.0f} 円",
            f"  平均損失        : {self.avg_loss:>10,.0f} 円",
            f"  損益比 (RR)     : {self.payoff_ratio:>6.2f}",
            "-" * 62,
            f"  最大DD          : {self.max_drawdown * 100:>6.2f} % ({self.max_drawdown_yen:,.0f} 円)",
            f"  最大連敗        : {self.max_consecutive_losses:>6} 回",
            f"  シャープレシオ  : {self.sharpe:>6.2f}",
        ]
        if self.halt_reason:
            lines.append("-" * 62)
            lines.append(f"  ⚠ 途中停止      : {self.halt_reason}")
        if self.blocked:
            lines.append("-" * 62)
            lines.append(f"  リスク管理による見送り: {len(self.blocked)} 回")
            for when, reason in self.blocked[:5]:
                lines.append(f"    {when:%Y-%m-%d %H:%M}  {reason}")
            if len(self.blocked) > 5:
                lines.append(f"    ... 他 {len(self.blocked) - 5} 件")
        lines.append("=" * 62)
        return "\n".join(lines)

    def trade_table(self, limit: int = 20) -> str:
        if not self.trades:
            return "トレードなし"
        rows = [
            f"{'#':>3} {'方向':<4} {'数量':>8} {'建値':>9} {'決済':>9} "
            f"{'pips':>8} {'損益(円)':>11}  理由"
        ]
        for i, t in enumerate(self.trades[:limit], 1):
            rows.append(
                f"{i:>3} {t.side.value:<4} {t.units:>8,} {t.entry_price:>9.3f} "
                f"{t.exit_price:>9.3f} {t.pips:>8.1f} {t.pnl:>11,.0f}  {t.exit_reason}"
            )
        if len(self.trades) > limit:
            rows.append(f"... 他 {len(self.trades) - limit} トレード")
        return "\n".join(rows)


def run_backtest(
    candles: Sequence[Candle],
    strategy: Strategy,
    instrument: Instrument,
    risk_config: Optional[RiskConfig] = None,
    starting_balance: float = 1_000_000.0,
    spread_pips: float = 0.4,
    slippage_pips: float = 0.2,
    commission_per_10k: float = 0.0,
    swap_per_10k_per_day: float = 0.0,
    close_at_end: bool = True,
) -> BacktestResult:
    """ヒストリカルデータで戦略を検証する。"""
    if not candles:
        raise ValueError("足データが空")

    risk_config = risk_config or RiskConfig()
    broker = PaperBroker(
        starting_balance=starting_balance,
        spread_pips=spread_pips,
        slippage_pips=slippage_pips,
        commission_per_10k=commission_per_10k,
        swap_per_10k_per_day=swap_per_10k_per_day,
    )
    broker.connect()
    risk = RiskManager(risk_config, starting_balance)
    blocked: List[Tuple[datetime, str]] = []

    for candle in candles:
        # 1) この足の値動きで損切り・利確を先に処理する。
        #    新しい判断より既存建玉の決済が優先。
        for trade in broker.process_candle(candle, instrument):
            risk.on_trade_closed(trade.pnl)

        equity = broker.get_equity()
        risk.on_new_bar(candle.time, equity)

        # 2) 戦略に足を渡す
        strategy.feed(candle)
        positions = broker.get_positions(instrument)
        position = positions[0] if positions else None

        # 3) トレーリングストップの更新
        if position is not None:
            risk.update_trailing_stop(position, candle.close)

        signal = strategy.on_candle(position)

        # 4) 手仕舞い
        if signal.type is SignalType.EXIT and position is not None:
            trade = broker.close_position(position, signal.reason or "戦略シグナル")
            risk.on_trade_closed(trade.pnl)
            continue

        # 5) 新規建玉
        if signal.is_entry and position is None:
            side = signal.side
            assert side is not None
            decision = risk.evaluate_entry(
                instrument=instrument,
                side=side,
                entry_price=candle.close,
                stop_price=signal.stop_price,
                equity=equity,
                open_positions=broker.get_positions(),
                now=candle.time,
                spread_pips=spread_pips,
            )
            if not decision:
                blocked.append((candle.time, decision.reason))
                continue

            stop = signal.stop_price
            if stop is None:
                offset = instrument.pips_to_price(risk_config.default_stop_pips)
                stop = candle.close - offset * side.sign
            broker.place_order(
                Order(
                    instrument=instrument,
                    side=side,
                    units=decision.units,
                    stop_price=stop,
                    take_profit_price=signal.take_profit_price,
                    reason=signal.reason,
                )
            )

    if close_at_end:
        for position in broker.get_positions():
            broker.close_position(position, "検証期間終了")

    return BacktestResult(
        trades=broker.trades,
        equity_curve=broker.equity_curve,
        starting_balance=starting_balance,
        final_balance=broker.balance,
        instrument=instrument,
        strategy_name=strategy.describe(),
        bars=len(candles),
        blocked=blocked,
        halt_reason=risk.state.halt_reason,
    )
