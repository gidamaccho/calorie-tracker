"""ドメインモデル定義。

金額はすべて円 (JPY) を基準に扱う。価格は通貨ペアの建値そのまま。
数量 (units) は「通貨単位」で表す。例: USD/JPY を 10000 units 買う = 1万通貨の買い。
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


class Side(enum.Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def sign(self) -> int:
        """買いなら +1、売りなら -1。損益計算の符号に使う。"""
        return 1 if self is Side.BUY else -1

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY


class OrderType(enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class SignalType(enum.Enum):
    ENTRY_LONG = "ENTRY_LONG"
    ENTRY_SHORT = "ENTRY_SHORT"
    EXIT = "EXIT"
    NONE = "NONE"


@dataclass(frozen=True)
class Instrument:
    """通貨ペアの仕様。

    pip: 1pip の価格差。USD/JPY なら 0.01、EUR/USD なら 0.0001。
    quote_is_jpy: 決済通貨が円かどうか。円建てなら損益 = 値幅 * units でそのまま円になる。
    min_units / units_step: 業者が受け付ける最小取引単位と刻み。
      SBI証券FXα は 10000 通貨単位、SBI FXトレードは 1 通貨単位。
    """

    symbol: str
    pip: float = 0.01
    quote_is_jpy: bool = True
    min_units: int = 1000
    units_step: int = 1000
    max_leverage: float = 25.0  # 国内の個人口座は法令で25倍が上限

    def price_to_pips(self, price_diff: float) -> float:
        return price_diff / self.pip

    def pips_to_price(self, pips: float) -> float:
        return pips * self.pip

    def round_units(self, units: float) -> int:
        """業者が受け付ける単位に切り下げる。最小単位未満なら 0 (=発注しない)。"""
        if units < self.min_units:
            return 0
        return int(units // self.units_step) * self.units_step


# よく使うペアのプリセット
USDJPY = Instrument("USD/JPY", pip=0.01, quote_is_jpy=True)
EURJPY = Instrument("EUR/JPY", pip=0.01, quote_is_jpy=True)
GBPJPY = Instrument("GBP/JPY", pip=0.01, quote_is_jpy=True)
EURUSD = Instrument("EUR/USD", pip=0.0001, quote_is_jpy=False)

PRESETS = {i.symbol: i for i in (USDJPY, EURJPY, GBPJPY, EURUSD)}


@dataclass(frozen=True)
class Candle:
    """確定した1本のローソク足。エンジンは未確定足では判断しない。"""

    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def __post_init__(self) -> None:
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise ValueError(
                f"不正なローソク足 {self.time}: O={self.open} H={self.high} "
                f"L={self.low} C={self.close}"
            )

    @property
    def typical(self) -> float:
        return (self.high + self.low + self.close) / 3.0

    @property
    def range(self) -> float:
        return self.high - self.low


@dataclass
class Signal:
    """戦略がエンジンに返す売買判断。

    stop_price / take_profit_price は絶対価格。戦略側が None を返した場合は
    リスク管理側の既定値 (ATR倍率など) が使われる。
    """

    type: SignalType
    reason: str = ""
    stop_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    confidence: float = 1.0

    @classmethod
    def none(cls) -> "Signal":
        return cls(SignalType.NONE)

    @property
    def is_entry(self) -> bool:
        return self.type in (SignalType.ENTRY_LONG, SignalType.ENTRY_SHORT)

    @property
    def side(self) -> Optional[Side]:
        if self.type is SignalType.ENTRY_LONG:
            return Side.BUY
        if self.type is SignalType.ENTRY_SHORT:
            return Side.SELL
        return None


@dataclass
class Order:
    instrument: Instrument
    side: Side
    units: int
    type: OrderType = OrderType.MARKET
    price: Optional[float] = None          # 指値/逆指値の価格
    stop_price: Optional[float] = None      # 建玉に付ける損切り
    take_profit_price: Optional[float] = None
    reason: str = ""
    client_id: str = ""


@dataclass
class Position:
    instrument: Instrument
    side: Side
    units: int
    entry_price: float
    entry_time: datetime
    stop_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    reason: str = ""
    # トレーリングストップ用に、建玉が到達した最良値を記録する
    best_price: float = field(default=0.0)

    def __post_init__(self) -> None:
        if self.best_price == 0.0:
            self.best_price = self.entry_price

    def unrealized_pnl(self, price: float, jpy_rate: float = 1.0) -> float:
        """評価損益 (円)。

        jpy_rate は決済通貨→円の換算レート。円建てペアなら 1.0。
        """
        rate = 1.0 if self.instrument.quote_is_jpy else jpy_rate
        return (price - self.entry_price) * self.side.sign * self.units * rate

    def notional(self, price: float, jpy_rate: float = 1.0) -> float:
        """想定元本 (円)。証拠金計算に使う。"""
        rate = 1.0 if self.instrument.quote_is_jpy else jpy_rate
        return abs(price * self.units * rate)

    def required_margin(self, price: float, jpy_rate: float = 1.0) -> float:
        return self.notional(price, jpy_rate) / self.instrument.max_leverage

    def update_trailing(self, price: float) -> None:
        if self.side is Side.BUY:
            self.best_price = max(self.best_price, price)
        else:
            self.best_price = min(self.best_price, price)


@dataclass
class Trade:
    """決済済みの1トレード。"""

    instrument: Instrument
    side: Side
    units: int
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    pnl: float                  # 手数料・スプレッド込みの確定損益 (円)
    exit_reason: str = ""
    entry_reason: str = ""

    @property
    def pips(self) -> float:
        return self.instrument.price_to_pips(
            (self.exit_price - self.entry_price) * self.side.sign
        )

    @property
    def is_win(self) -> bool:
        return self.pnl > 0

    @property
    def duration_hours(self) -> float:
        return (self.exit_time - self.entry_time).total_seconds() / 3600.0


@dataclass
class Tick:
    """現在値。Bid/Ask を持つ。"""

    time: datetime
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    if b == 0 or math.isnan(b):
        return default
    return a / b
