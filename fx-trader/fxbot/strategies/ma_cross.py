import pandas as pd

from ..indicators import ema, sma
from .base import BUY, NONE, SELL, Strategy


class MACrossStrategy(Strategy):
    """移動平均クロス(トレンドフォロー)。

    短期線が長期線を上抜け → 買い、下抜け → 売り。
    params: fast(短期期間), slow(長期期間), ma_type("ema" または "sma")
    """

    name = "ma_cross"

    def __init__(self, fast: int = 20, slow: int = 50, ma_type: str = "ema"):
        if fast >= slow:
            raise ValueError("fast は slow より小さくしてください")
        if ma_type not in ("ema", "sma"):
            raise ValueError("ma_type は 'ema' か 'sma' です")
        super().__init__(fast=fast, slow=slow, ma_type=ma_type)
        self.fast = fast
        self.slow = slow
        self.ma = ema if ma_type == "ema" else sma

    @property
    def min_bars(self) -> int:
        return self.slow + 2

    def signals(self, df: pd.DataFrame) -> pd.Series:
        fast = self.ma(df["close"], self.fast)
        slow = self.ma(df["close"], self.slow)
        above = fast > slow
        prev_above = above.shift(1)
        valid = slow.notna() & slow.shift(1).notna()

        out = pd.Series(NONE, index=df.index, dtype=int)
        out[valid & above & (prev_above == False)] = BUY  # noqa: E712
        out[valid & ~above & (prev_above == True)] = SELL  # noqa: E712
        return out
