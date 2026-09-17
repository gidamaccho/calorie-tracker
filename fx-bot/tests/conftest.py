import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fxbot.models import Candle, USDJPY  # noqa: E402

T0 = datetime(2024, 3, 4, 0, 0, tzinfo=timezone.utc)  # 月曜


@pytest.fixture
def instrument():
    return USDJPY


def make_candles(closes, start=T0, step_minutes=60, wick=0.05):
    """終値の列からローソク足を作る。高値安値は始値終値の外側に置く。"""
    candles = []
    prev = closes[0]
    t = start
    for close in closes:
        high = max(prev, close) + wick
        low = min(prev, close) - wick
        candles.append(Candle(time=t, open=prev, high=high, low=low, close=close))
        prev = close
        t += timedelta(minutes=step_minutes)
        while t.weekday() >= 5:
            t += timedelta(days=1)
    return candles


@pytest.fixture
def candle_factory():
    return make_candles
