"""バックテスト。

約定ルール(なるべく現実寄り・保守的に):
  - シグナルは足の確定(終値)で判定し、次の足の始値で約定する
  - チャートの価格は Bid。買いは Ask(= Bid + スプレッド)で入り Bid で出る、売りはその逆
  - 損切り/利確は足の高値・安値で判定。同じ足で両方に届いた場合は損切りを優先
  - 窓開けで損切りを飛び越えた場合は始値で決済
  - 反対シグナルが出たら決済してドテン
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import BacktestConfig, RiskConfig
from .indicators import atr
from .risk import DailyLossGuard, calc_lots, pip_size
from .strategies import Strategy


@dataclass
class Trade:
    direction: int
    entry_time: pd.Timestamp
    entry_price: float
    lots: float
    sl: float
    tp: float
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    reason: str = ""
    pnl: float = 0.0


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity: pd.Series
    initial_balance: float
    stats: dict = field(default_factory=dict)

    def trades_frame(self) -> pd.DataFrame:
        return pd.DataFrame([t.__dict__ for t in self.trades])


def run_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    risk: RiskConfig,
    bt: BacktestConfig,
    symbol: str,
) -> BacktestResult:
    spread = bt.spread_pips * pip_size(symbol)
    value_per_price = bt.contract_size * bt.quote_to_account_rate
    signals = strategy.signals(df).fillna(0).astype(int).to_numpy()
    atr_vals = atr(df, risk.atr_period).to_numpy()
    o, h, l, c = (df[col].to_numpy() for col in ("open", "high", "low", "close"))
    times = df.index

    balance = bt.initial_balance
    guard = DailyLossGuard(risk.max_daily_loss_pct)
    pos: Trade | None = None
    pending = 0  # 前の足で出たシグナル(この足の始値で執行)
    trades: list[Trade] = []
    equity = np.empty(len(df))

    def close(trade: Trade, i: int, bid_price: float, reason: str) -> None:
        nonlocal balance
        # 買いは Bid で、売りは Ask で決済
        exit_price = bid_price if trade.direction == 1 else bid_price + spread
        trade.exit_time = times[i]
        trade.exit_price = exit_price
        trade.reason = reason
        trade.pnl = (exit_price - trade.entry_price) * trade.direction * trade.lots * value_per_price
        balance += trade.pnl
        trades.append(trade)

    for i in range(len(df)):
        # 1) 前の足のシグナルを始値で執行
        if pending:
            if pos and pos.direction != pending:
                close(pos, i, o[i], "reverse")
                pos = None
            a = atr_vals[i - 1]
            if pos is None and np.isfinite(a) and a > 0 and guard.can_open(times[i].date(), balance):
                sl_dist = a * risk.sl_atr_mult
                lots = calc_lots(balance, risk.risk_per_trade_pct, sl_dist, value_per_price,
                                 bt.min_lot, bt.lot_step, bt.max_lot)
                if lots > 0:
                    entry = o[i] + spread if pending == 1 else o[i]
                    pos = Trade(
                        direction=pending, entry_time=times[i], entry_price=entry, lots=lots,
                        sl=entry - pending * sl_dist, tp=entry + pending * a * risk.tp_atr_mult,
                    )
            pending = 0

        # 2) 損切り・利確の判定(買いは Bid、売りは Ask = Bid + spread で判定)
        if pos:
            if pos.direction == 1:
                if l[i] <= pos.sl:
                    close(pos, i, min(o[i], pos.sl), "stop_loss")
                    pos = None
                elif h[i] >= pos.tp:
                    close(pos, i, max(o[i], pos.tp), "take_profit")
                    pos = None
            else:
                if h[i] + spread >= pos.sl:
                    close(pos, i, max(o[i], pos.sl - spread), "stop_loss")
                    pos = None
                elif l[i] + spread <= pos.tp:
                    close(pos, i, min(o[i], pos.tp - spread), "take_profit")
                    pos = None

        # 3) この足の確定でシグナル判定(最後の足では次の足が無いので見送り)
        s = signals[i]
        if s and i < len(df) - 1 and (pos is None or pos.direction != s):
            pending = s

        # 4) 時価評価
        floating = 0.0
        if pos:
            exit_now = c[i] if pos.direction == 1 else c[i] + spread
            floating = (exit_now - pos.entry_price) * pos.direction * pos.lots * value_per_price
        equity[i] = balance + floating

    if pos:
        close(pos, len(df) - 1, c[-1], "end_of_data")
        equity[-1] = balance

    result = BacktestResult(trades, pd.Series(equity, index=times), bt.initial_balance)
    result.stats = compute_stats(result)
    return result


def compute_stats(result: BacktestResult) -> dict:
    pnls = np.array([t.pnl for t in result.trades])
    eq = result.equity
    peak = eq.cummax()
    drawdown = ((eq - peak) / peak).min() * 100 if len(eq) else 0.0
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    final = float(eq.iloc[-1]) if len(eq) else result.initial_balance
    return {
        "初期資金": result.initial_balance,
        "最終資金": round(final, 2),
        "損益": round(final - result.initial_balance, 2),
        "リターン(%)": round((final / result.initial_balance - 1) * 100, 2),
        "取引回数": int(len(pnls)),
        "勝率(%)": round(len(wins) / len(pnls) * 100, 2) if len(pnls) else 0.0,
        "プロフィットファクター": round(wins.sum() / -losses.sum(), 2) if len(losses) else float("inf") if len(wins) else 0.0,
        "平均損益": round(pnls.mean(), 2) if len(pnls) else 0.0,
        "最大ドローダウン(%)": round(float(drawdown), 2),
    }
