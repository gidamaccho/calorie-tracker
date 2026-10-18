"""戦略レジストリ。新しい戦略は Strategy を継承して STRATEGIES に追加するだけで使える。"""
from .base import BUY, NONE, SELL, Strategy
from .ma_cross import MACrossStrategy
from .rsi_reversal import RSIReversalStrategy

STRATEGIES: dict[str, type[Strategy]] = {
    MACrossStrategy.name: MACrossStrategy,
    RSIReversalStrategy.name: RSIReversalStrategy,
}


def create_strategy(name: str, params: dict | None = None) -> Strategy:
    try:
        cls = STRATEGIES[name]
    except KeyError:
        raise ValueError(f"不明な戦略: {name}(使えるもの: {', '.join(STRATEGIES)})") from None
    return cls(**(params or {}))


__all__ = ["BUY", "SELL", "NONE", "Strategy", "STRATEGIES", "create_strategy"]
