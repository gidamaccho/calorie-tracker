"""取引記録。

自動売買で最も重要なのは「後から何が起きたか完全に再現できること」。
発注・約定・決済・見送り・エラーをすべて追記専用のファイルに残す。
"""

from __future__ import annotations

import csv
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from .models import Position, Trade, utcnow

log = logging.getLogger(__name__)

TRADE_COLUMNS = [
    "exit_time", "symbol", "side", "units", "entry_time", "entry_price",
    "exit_price", "pips", "pnl", "entry_reason", "exit_reason",
]


class Journal:
    """トレードを CSV に、イベントを JSONL に追記する。"""

    def __init__(self, directory: str = "./journal", enabled: bool = True) -> None:
        self.directory = directory
        self.enabled = enabled
        self.trades_path = os.path.join(directory, "trades.csv")
        self.events_path = os.path.join(directory, "events.jsonl")
        if enabled:
            os.makedirs(directory, exist_ok=True)
            self._ensure_header()

    def _ensure_header(self) -> None:
        if os.path.exists(self.trades_path) and os.path.getsize(self.trades_path) > 0:
            return
        with open(self.trades_path, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow(TRADE_COLUMNS)

    def record_trade(self, trade: Trade) -> None:
        if not self.enabled:
            return
        with open(self.trades_path, "a", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow([
                trade.exit_time.isoformat(),
                trade.instrument.symbol,
                trade.side.value,
                trade.units,
                trade.entry_time.isoformat(),
                f"{trade.entry_price:.5f}",
                f"{trade.exit_price:.5f}",
                f"{trade.pips:.1f}",
                f"{trade.pnl:.2f}",
                trade.entry_reason,
                trade.exit_reason,
            ])
        self.event("trade_closed", symbol=trade.instrument.symbol,
                   pnl=round(trade.pnl, 2), pips=round(trade.pips, 1),
                   reason=trade.exit_reason)

    def record_position(self, position: Position) -> None:
        self.event(
            "position_opened",
            symbol=position.instrument.symbol,
            side=position.side.value,
            units=position.units,
            entry_price=position.entry_price,
            stop=position.stop_price,
            take_profit=position.take_profit_price,
            reason=position.reason,
        )

    def event(self, kind: str, **fields: Any) -> None:
        """任意のイベントを1行の JSON として残す。"""
        if not self.enabled:
            return
        record: Dict[str, Any] = {
            "time": utcnow().isoformat(),
            "kind": kind,
            **{k: _jsonable(v) for k, v in fields.items()},
        }
        try:
            with open(self.events_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:  # 記録の失敗で取引を止めない
            log.warning("イベント記録に失敗: %s", exc)


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):  # Enum
        return value.value
    return value


def setup_logging(level: str = "INFO", logfile: Optional[str] = None) -> None:
    handlers: list = [logging.StreamHandler()]
    if logfile:
        os.makedirs(os.path.dirname(logfile) or ".", exist_ok=True)
        handlers.append(logging.FileHandler(logfile, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )
