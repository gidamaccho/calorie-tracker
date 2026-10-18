from abc import ABC, abstractmethod

import pandas as pd

BUY = 1
SELL = -1
NONE = 0


class Strategy(ABC):
    """売買戦略の基底クラス。

    signals() は各足の「確定した終値時点」でのエントリーシグナルを返す。
      1 = 買い, -1 = 売り, 0 = 何もしない
    i 番目の値は 0..i 番目の足だけから計算すること(未来参照禁止)。
    損切り・利確幅は戦略ではなくリスク設定(ATR 倍率)で決める。
    """

    name: str = ""

    def __init__(self, **params):
        self.params = params

    @property
    @abstractmethod
    def min_bars(self) -> int:
        """シグナル計算に最低限必要な足の本数。"""

    @abstractmethod
    def signals(self, df: pd.DataFrame) -> pd.Series:
        """df(open/high/low/close)から int のシグナル列を返す。"""

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.__class__.__name__}({args})"
