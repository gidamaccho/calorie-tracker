"""資金管理: ロット計算と日次損失ストップ。"""
import math
from datetime import date


def pip_size(symbol: str) -> float:
    """JPY 絡みは 0.01、それ以外は 0.0001。"""
    return 0.01 if "JPY" in symbol.upper() else 0.0001


def calc_lots(
    equity: float,
    risk_pct: float,
    sl_distance: float,
    value_per_price_per_lot: float,
    min_lot: float,
    lot_step: float,
    max_lot: float,
) -> float:
    """損切りに掛かったとき equity の risk_pct% を失うロット数を返す。

    value_per_price_per_lot: 価格が 1.0 動いたときの 1 ロットあたり損益(口座通貨)。
    最小ロットに満たない場合は 0(=取引しない)。リスクを超えないよう切り捨てる。
    """
    if sl_distance <= 0 or value_per_price_per_lot <= 0 or equity <= 0:
        return 0.0
    risk_amount = equity * risk_pct / 100
    raw = risk_amount / (sl_distance * value_per_price_per_lot)
    lots = math.floor(raw / lot_step + 1e-9) * lot_step
    lots = min(lots, max_lot)
    if lots < min_lot:
        return 0.0
    # 浮動小数の誤差を lot_step の桁で丸める
    digits = max(0, -int(math.floor(math.log10(lot_step))))
    return round(lots, digits)


class DailyLossGuard:
    """その日の開始時点から max_loss_pct% 以上減ったら、その日の新規エントリーを止める。"""

    def __init__(self, max_loss_pct: float):
        self.max_loss_pct = max_loss_pct
        self.day: date | None = None
        self.start_equity = 0.0

    def can_open(self, today: date, equity: float) -> bool:
        if self.day != today:
            self.day = today
            self.start_equity = equity
        if self.max_loss_pct <= 0 or self.start_equity <= 0:
            return True
        loss_pct = (self.start_equity - equity) / self.start_equity * 100
        return loss_pct < self.max_loss_pct
