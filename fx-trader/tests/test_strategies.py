import pandas as pd
import pytest

from fxbot.data import synthetic_ohlc
from fxbot.strategies import STRATEGIES, create_strategy


def frame(closes):
    c = pd.Series(closes, dtype=float).to_numpy()
    return pd.DataFrame({"open": c, "high": c + 0.1, "low": c - 0.1, "close": c},
                        index=pd.date_range("2024-01-01", periods=len(c), freq="h"))


def test_ma_cross_signals_on_cross():
    closes = [10] * 10 + [9] * 5 + [12] * 5 + [8] * 5
    sig = create_strategy("ma_cross", {"fast": 2, "slow": 5, "ma_type": "sma"}).signals(frame(closes))
    assert 1 in sig.values and -1 in sig.values
    # 最初の買いは上昇が始まった後、最初の売りはその後
    assert sig[sig == 1].index[0] < sig[sig == -1].index[-1]


def test_rsi_reversal_buy_after_oversold():
    closes = [100 - i for i in range(30)] + [70 + i * 2 for i in range(10)]
    sig = create_strategy("rsi_reversal", {"period": 5}).signals(frame(closes))
    first_buy = sig[sig == 1].index[0]
    assert first_buy >= sig.index[30]


@pytest.mark.parametrize("name", list(STRATEGIES))
def test_no_lookahead(name):
    """途中までのデータで計算したシグナルが、全データで計算したものと一致すること。"""
    df = synthetic_ohlc(600, seed=3)
    strat = create_strategy(name)
    full = strat.signals(df)
    for k in (100, 250, 599):
        assert strat.signals(df.iloc[:k]).equals(full.iloc[:k])


def test_unknown_strategy():
    with pytest.raises(ValueError):
        create_strategy("nope")
