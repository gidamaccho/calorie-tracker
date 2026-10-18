import numpy as np
import pandas as pd

from fxbot.indicators import atr, rsi, sma


def test_sma():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    assert sma(s, 3).tolist()[2:] == [2.0, 3.0, 4.0]
    assert np.isnan(sma(s, 3).iloc[1])


def test_rsi_extremes():
    up = pd.Series(np.arange(1, 40), dtype=float)
    assert rsi(up, 14).iloc[-1] == 100.0
    down = pd.Series(np.arange(40, 1, -1), dtype=float)
    assert rsi(down, 14).iloc[-1] == 0.0


def test_atr_constant_range():
    n = 50
    df = pd.DataFrame({"open": [100.0] * n, "high": [100.5] * n, "low": [99.5] * n, "close": [100.0] * n})
    assert abs(atr(df, 14).iloc[-1] - 1.0) < 1e-9
