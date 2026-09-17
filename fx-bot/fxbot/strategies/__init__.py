"""戦略レジストリ。設定ファイルの名前から戦略クラスを引く。"""

from __future__ import annotations

from typing import Any, Dict, Type

from ..models import Instrument
from .base import Strategy
from .breakout import BreakoutStrategy
from .rsi_reversion import RsiReversionStrategy
from .sma_cross import SmaCrossStrategy

REGISTRY: Dict[str, Type[Strategy]] = {
    SmaCrossStrategy.name: SmaCrossStrategy,
    RsiReversionStrategy.name: RsiReversionStrategy,
    BreakoutStrategy.name: BreakoutStrategy,
}


def build_strategy(name: str, instrument: Instrument, params: Dict[str, Any] | None = None) -> Strategy:
    if name not in REGISTRY:
        available = ", ".join(sorted(REGISTRY))
        raise KeyError(f"未知の戦略 '{name}'。利用可能: {available}")
    return REGISTRY[name](instrument, **(params or {}))


__all__ = [
    "Strategy",
    "SmaCrossStrategy",
    "RsiReversionStrategy",
    "BreakoutStrategy",
    "REGISTRY",
    "build_strategy",
]
