"""fxbot — FX自動売買フレームワーク。

バックテスト・ペーパートレード・実弾稼働を同じ戦略コードで回す。
ブローカーの差は brokers/ 以下に閉じ込めてある。
"""

__version__ = "0.1.0"

from .models import (
    Candle, Instrument, Order, Position, Side, Signal, SignalType, Tick, Trade,
)
from .risk import RiskConfig, RiskManager

__all__ = [
    "Candle", "Instrument", "Order", "Position", "Side", "Signal",
    "SignalType", "Tick", "Trade", "RiskConfig", "RiskManager", "__version__",
]
