"""ブローカー抽象。

エンジンはこのインターフェースしか知らない。
ペーパー / SBI / OANDA の差はすべてこの下に閉じ込める。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ..models import Instrument, Order, Position, Tick, Trade


class BrokerError(RuntimeError):
    """発注・取消・接続の失敗。エンジンはこれを捕捉して取引を止める。"""


class Broker(ABC):
    """発注と建玉管理の窓口。"""

    #: 実弾が動くか。True の場合、エンジンは起動時に明示的な確認を要求する。
    is_live: bool = False

    @abstractmethod
    def connect(self) -> None:
        """接続・ログイン。冪等に実装すること。"""

    @abstractmethod
    def disconnect(self) -> None:
        """切断。例外を投げないこと (終了処理で呼ばれる)。"""

    @abstractmethod
    def get_tick(self, instrument: Instrument) -> Tick:
        """現在の Bid/Ask を取得する。"""

    @abstractmethod
    def get_equity(self) -> float:
        """有効証拠金 (円)。評価損益を含む。"""

    @abstractmethod
    def get_positions(self, instrument: Optional[Instrument] = None) -> List[Position]:
        """保有建玉。"""

    @abstractmethod
    def place_order(self, order: Order) -> Position:
        """新規建玉。約定した Position を返す。失敗時は BrokerError。"""

    @abstractmethod
    def close_position(self, position: Position, reason: str = "") -> Trade:
        """建玉を決済し、確定した Trade を返す。"""

    def close_all(self, reason: str = "全決済") -> List[Trade]:
        """全建玉を決済する。緊急停止時に使う。"""
        return [self.close_position(p, reason) for p in list(self.get_positions())]

    def poll_closed_trades(self) -> List[Trade]:
        """前回の呼び出し以降に「業者側で」決済された取引を返す。

        損切り・利確・ロスカットは、こちらが close_position を呼ばずに
        約定する。これを回収しないと、リスク管理の連敗カウントにも
        取引記録にも載らず、最も重要な決済が見えないままになる。

        既定は空リスト。実装しないブローカーでは、決済の検知は
        次回の get_positions のズレでしか分からない点に注意。
        """
        return []

    def modify_position(self, position: Position) -> None:
        """損切り・利確価格の変更を業者側へ反映する。

        既定では何もしない。ペーパーブローカーは Position オブジェクトを
        そのまま持っているため不要。実ブローカーは要実装。
        """
        return None

    def __enter__(self) -> "Broker":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.disconnect()
