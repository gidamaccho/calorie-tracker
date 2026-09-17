"""リスク管理。自動売買で口座を飛ばさないための最後の砦。

戦略が何を言おうと、ここを通らない注文は出さない。
- 1トレードあたりの損失を口座の一定割合に固定する (ポジションサイズ計算)
- 1日の損失上限、連敗数、最大ドローダウンで取引を停止する
- レバレッジ上限・証拠金維持率をチェックする
- 取引時間帯フィルタ (流動性の薄い時間を避ける)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import List, Optional, Tuple

from .models import Instrument, Position, Side, safe_div


@dataclass
class RiskConfig:
    """リスク設定。既定値は保守的に寄せてある。"""

    risk_per_trade: float = 0.01          # 1トレードで許容する口座比率 (1%)
    max_positions: int = 1                # 同時保有建玉数
    max_leverage: float = 5.0             # 実効レバレッジの自主上限 (法定25倍より厳しく)
    daily_loss_limit: float = 0.03        # 1日の損失がこの比率に達したら当日停止
    max_drawdown: float = 0.20            # 資産ピークからこの比率下がったら全停止
    max_consecutive_losses: int = 5       # 連敗数の上限
    min_stop_pips: float = 3.0            # これより狭い損切りは拒否 (スプレッド負け防止)
    max_stop_pips: float = 200.0          # これより広い損切りは拒否 (想定外の建玉サイズ防止)
    default_stop_pips: float = 20.0       # 戦略が損切りを指定しなかった場合
    trailing_stop_pips: float = 0.0       # 0 = トレーリングなし
    trailing_trigger_pips: float = 0.0    # 含み益がこれを超えてからトレーリング開始
    trading_hours: Optional[Tuple[int, int]] = None  # UTC時 [開始, 終了)
    trade_on_weekend: bool = False        # 土日 (UTC) の発注を許可するか
    max_spread_pips: float = 3.0          # スプレッドがこれより広いときは発注しない


class RiskDecision:
    """発注可否の判断結果。"""

    def __init__(self, allowed: bool, units: int = 0, reason: str = "") -> None:
        self.allowed = allowed
        self.units = units
        self.reason = reason

    def __bool__(self) -> bool:
        return self.allowed

    def __repr__(self) -> str:
        status = "許可" if self.allowed else "拒否"
        return f"<RiskDecision {status} units={self.units} {self.reason}>"


@dataclass
class RiskState:
    """稼働中に更新される状態。日をまたぐとリセットされる項目がある。"""

    equity_peak: float = 0.0
    day: Optional[date] = None
    day_start_equity: float = 0.0
    day_realized_pnl: float = 0.0
    consecutive_losses: int = 0
    halted: bool = False
    halt_reason: str = ""
    blocked_reasons: List[str] = field(default_factory=list)


class RiskManager:
    def __init__(self, config: RiskConfig, starting_equity: float) -> None:
        self.config = config
        self.state = RiskState(
            equity_peak=starting_equity,
            day_start_equity=starting_equity,
        )

    # ------------------------------------------------------------------
    # 状態更新
    # ------------------------------------------------------------------
    def on_new_bar(self, now: datetime, equity: float) -> None:
        """足ごとに呼ぶ。日付の切り替わりと資産ピークを追跡する。"""
        today = now.date()
        if self.state.day != today:
            self.state.day = today
            self.state.day_start_equity = equity
            self.state.day_realized_pnl = 0.0
            # 日次の損失上限による停止は翌日解除する。
            # 最大DD・連敗による停止は手動で解除するまで残す。
            if self.state.halted and self.state.halt_reason.startswith("日次"):
                self.state.halted = False
                self.state.halt_reason = ""

        self.state.equity_peak = max(self.state.equity_peak, equity)

        drawdown = safe_div(
            self.state.equity_peak - equity, self.state.equity_peak, 0.0
        )
        if drawdown >= self.config.max_drawdown and not self.state.halted:
            self.halt(
                f"最大ドローダウン超過 ({drawdown:.1%} >= {self.config.max_drawdown:.1%})"
            )

        day_loss = safe_div(
            self.state.day_start_equity - equity, self.state.day_start_equity, 0.0
        )
        if day_loss >= self.config.daily_loss_limit and not self.state.halted:
            self.halt(
                f"日次損失上限に到達 ({day_loss:.1%} >= {self.config.daily_loss_limit:.1%})"
            )

    def on_trade_closed(self, pnl: float) -> None:
        self.state.day_realized_pnl += pnl
        if pnl < 0:
            self.state.consecutive_losses += 1
            if self.state.consecutive_losses >= self.config.max_consecutive_losses:
                self.halt(f"{self.state.consecutive_losses}連敗")
        else:
            self.state.consecutive_losses = 0

    def halt(self, reason: str) -> None:
        self.state.halted = True
        self.state.halt_reason = reason

    def resume(self) -> None:
        self.state.halted = False
        self.state.halt_reason = ""
        self.state.consecutive_losses = 0

    # ------------------------------------------------------------------
    # 発注前チェック
    # ------------------------------------------------------------------
    def evaluate_entry(
        self,
        instrument: Instrument,
        side: Side,
        entry_price: float,
        stop_price: Optional[float],
        equity: float,
        open_positions: List[Position],
        now: datetime,
        spread_pips: float = 0.0,
        jpy_rate: float = 1.0,
    ) -> RiskDecision:
        """新規建玉の可否と数量を決める。"""
        cfg = self.config

        if self.state.halted:
            return RiskDecision(False, reason=f"取引停止中: {self.state.halt_reason}")

        if equity <= 0:
            return RiskDecision(False, reason="有効証拠金がゼロ以下")

        if len(open_positions) >= cfg.max_positions:
            return RiskDecision(
                False, reason=f"建玉数の上限 ({cfg.max_positions}) に到達"
            )

        if not self._time_allowed(now):
            return RiskDecision(False, reason=f"取引時間外 ({now:%Y-%m-%d %H:%M} UTC)")

        if spread_pips > cfg.max_spread_pips:
            return RiskDecision(
                False,
                reason=f"スプレッド拡大 ({spread_pips:.1f} > {cfg.max_spread_pips:.1f} pips)",
            )

        # 損切り価格が未指定なら既定の pips 幅を当てる
        if stop_price is None:
            offset = instrument.pips_to_price(cfg.default_stop_pips)
            stop_price = entry_price - offset * side.sign

        stop_distance = abs(entry_price - stop_price)
        stop_pips = instrument.price_to_pips(stop_distance)

        # 損切りが建値の逆側にある (= 即損切りになる) 注文を弾く
        if (side is Side.BUY and stop_price >= entry_price) or (
            side is Side.SELL and stop_price <= entry_price
        ):
            return RiskDecision(
                False,
                reason=f"損切り価格 {stop_price:.3f} が建値 {entry_price:.3f} の誤った側にある",
            )

        if stop_pips < cfg.min_stop_pips:
            return RiskDecision(
                False, reason=f"損切り幅が狭すぎる ({stop_pips:.1f} < {cfg.min_stop_pips} pips)"
            )
        if stop_pips > cfg.max_stop_pips:
            return RiskDecision(
                False, reason=f"損切り幅が広すぎる ({stop_pips:.1f} > {cfg.max_stop_pips} pips)"
            )

        units = self.position_size(
            instrument, entry_price, stop_distance, equity, jpy_rate
        )
        if units <= 0:
            return RiskDecision(
                False,
                reason=(
                    f"必要数量が最小取引単位 ({instrument.min_units}) 未満。"
                    f"資金か損切り幅を見直すこと"
                ),
            )

        # レバレッジ上限。既存建玉の想定元本も合算する
        rate = 1.0 if instrument.quote_is_jpy else jpy_rate
        new_notional = entry_price * units * rate
        existing = sum(p.notional(entry_price, jpy_rate) for p in open_positions)
        total_leverage = safe_div(new_notional + existing, equity, float("inf"))
        if total_leverage > cfg.max_leverage:
            # 上限に収まるところまで数量を落とす
            allowed_notional = max(cfg.max_leverage * equity - existing, 0.0)
            units = instrument.round_units(safe_div(allowed_notional, entry_price * rate))
            if units <= 0:
                return RiskDecision(
                    False,
                    reason=(
                        f"レバレッジ上限 {cfg.max_leverage}倍 に抵触 "
                        f"(必要 {total_leverage:.1f}倍)"
                    ),
                )

        return RiskDecision(
            True,
            units=units,
            reason=f"リスク {cfg.risk_per_trade:.1%} / 損切り {stop_pips:.1f}pips",
        )

    def position_size(
        self,
        instrument: Instrument,
        entry_price: float,
        stop_distance: float,
        equity: float,
        jpy_rate: float = 1.0,
    ) -> int:
        """損失額が口座の risk_per_trade に収まる数量を返す。

        損失額(円) = 損切り幅 * 数量 * (決済通貨→円レート)
        なので 数量 = 許容損失額 / (損切り幅 * レート)。
        """
        if stop_distance <= 0:
            return 0
        risk_amount = equity * self.config.risk_per_trade
        rate = 1.0 if instrument.quote_is_jpy else jpy_rate
        raw_units = safe_div(risk_amount, stop_distance * rate, 0.0)
        return instrument.round_units(raw_units)

    def update_trailing_stop(self, position: Position, price: float) -> bool:
        """トレーリングストップを更新する。更新したら True。"""
        cfg = self.config
        if cfg.trailing_stop_pips <= 0:
            return False

        position.update_trailing(price)
        gain = (position.best_price - position.entry_price) * position.side.sign
        trigger = position.instrument.pips_to_price(cfg.trailing_trigger_pips)
        if gain < trigger:
            return False

        offset = position.instrument.pips_to_price(cfg.trailing_stop_pips)
        new_stop = position.best_price - offset * position.side.sign

        # ストップは利益方向にしか動かさない
        if position.stop_price is None:
            position.stop_price = new_stop
            return True
        if position.side is Side.BUY and new_stop > position.stop_price:
            position.stop_price = new_stop
            return True
        if position.side is Side.SELL and new_stop < position.stop_price:
            position.stop_price = new_stop
            return True
        return False

    # ------------------------------------------------------------------
    def _time_allowed(self, now: datetime) -> bool:
        cfg = self.config
        # 週末 (土日) は原則スキップ。実市場は土日休みだが、
        # 合成データやCSVの取り扱いで念のため明示的に制御する。
        if not cfg.trade_on_weekend and now.weekday() >= 5:
            return False
        if cfg.trading_hours is None:
            return True
        start, end = cfg.trading_hours
        hour = now.hour
        if start <= end:
            return start <= hour < end
        # 日付をまたぐ指定 (例: 22時〜翌6時)
        return hour >= start or hour < end
