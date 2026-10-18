import pandas as pd

from ..indicators import rsi
from .base import BUY, NONE, SELL, Strategy


class RSIReversalStrategy(Strategy):
    """RSI 逆張り。

    RSI が lower を下回った後に lower を上抜け → 買い、
    upper を上回った後に upper を下抜け → 売り。
    (売られすぎ・買われすぎから「戻り始めた」ところで入る)
    params: period, lower, upper
    """

    name = "rsi_reversal"

    def __init__(self, period: int = 14, lower: float = 30, upper: float = 70):
        if not 0 < lower < upper < 100:
            raise ValueError("0 < lower < upper < 100 にしてください")
        super().__init__(period=period, lower=lower, upper=upper)
        self.period = period
        self.lower = lower
        self.upper = upper

    @property
    def min_bars(self) -> int:
        return self.period + 2

    def signals(self, df: pd.DataFrame) -> pd.Series:
        r = rsi(df["close"], self.period)
        prev = r.shift(1)
        out = pd.Series(NONE, index=df.index, dtype=int)
        out[(prev < self.lower) & (r >= self.lower)] = BUY
        out[(prev > self.upper) & (r <= self.upper)] = SELL
        return out
