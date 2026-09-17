"""OANDA v20 REST アダプタ。

SBI証券と違い、OANDA証券は個人向けに公式のREST APIを提供している。
規約の範囲内で自動売買したい場合は、こちらが現実的な選択肢になる。

標準ライブラリの urllib のみで実装しているので追加依存はない。

使い方:
  export OANDA_TOKEN=...            # 口座管理画面で発行
  export OANDA_ACCOUNT_ID=101-...
  # 最初は必ずデモ環境 (practice) で動かすこと
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..models import Candle, Instrument, Order, Position, Side, Tick, Trade
from .base import Broker, BrokerError

log = logging.getLogger(__name__)

HOSTS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}


@dataclass
class OandaConfig:
    environment: str = "practice"   # "practice" (デモ) または "live" (実弾)
    token_env: str = "OANDA_TOKEN"
    account_env: str = "OANDA_ACCOUNT_ID"
    timeout: float = 20.0
    confirm_live_trading: bool = False

    @property
    def host(self) -> str:
        if self.environment not in HOSTS:
            raise BrokerError(f"environment は {list(HOSTS)} のいずれか: {self.environment}")
        return HOSTS[self.environment]


def to_oanda_symbol(instrument: Instrument) -> str:
    """'USD/JPY' -> 'USD_JPY'"""
    return instrument.symbol.replace("/", "_")


class OandaBroker(Broker):
    def __init__(self, config: OandaConfig) -> None:
        self.config = config
        self.is_live = config.environment == "live"
        if self.is_live and not config.confirm_live_trading:
            raise BrokerError(
                "environment='live' は実弾。confirm_live_trading=True を明示すること"
            )
        self._token = ""
        self._account = ""
        # 既に回収済みの決済ID。起動時に過去分を取り込まないよう connect で初期化する
        self._seen_closed: set = set()

    # ------------------------------------------------------------------
    def connect(self) -> None:
        self._token = os.environ.get(self.config.token_env, "")
        self._account = os.environ.get(self.config.account_env, "")
        if not self._token or not self._account:
            raise BrokerError(
                f"環境変数 {self.config.token_env} と {self.config.account_env} を設定すること"
            )
        summary = self._request("GET", f"/v3/accounts/{self._account}/summary")
        # 接続時点で既にある決済済み取引は「回収済み」としておく。
        # そうしないと、起動直後に過去の損益がリスク管理へ流れ込む。
        self._seen_closed = {t["id"] for t in self._fetch_closed_trades()}
        log.info(
            "OANDA (%s) に接続。残高=%s %s",
            self.config.environment,
            summary["account"]["balance"],
            summary["account"]["currency"],
        )

    def disconnect(self) -> None:
        self._token = ""

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = self.config.host + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept-Datetime-Format", "RFC3339")
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise BrokerError(f"OANDA API エラー {exc.code} {method} {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise BrokerError(f"OANDA API に接続できない: {exc.reason}") from exc

    # ------------------------------------------------------------------
    def get_tick(self, instrument: Instrument) -> Tick:
        symbol = to_oanda_symbol(instrument)
        query = urllib.parse.urlencode({"instruments": symbol})
        data = self._request("GET", f"/v3/accounts/{self._account}/pricing?{query}")
        prices = data.get("prices") or []
        if not prices:
            raise BrokerError(f"{symbol} の価格が取得できない")
        price = prices[0]
        if price.get("tradeable") is False:
            raise BrokerError(f"{symbol} は現在取引不可 (市場閉鎖)")
        bid = float(price["bids"][0]["price"])
        ask = float(price["asks"][0]["price"])
        return Tick(time=_parse_time(price["time"]), bid=bid, ask=ask)

    def get_equity(self) -> float:
        data = self._request("GET", f"/v3/accounts/{self._account}/summary")
        return float(data["account"]["NAV"])

    def get_positions(self, instrument: Optional[Instrument] = None) -> List[Position]:
        data = self._request("GET", f"/v3/accounts/{self._account}/openTrades")
        out: List[Position] = []
        for trade in data.get("trades", []):
            symbol = trade["instrument"].replace("_", "/")
            if instrument is not None and symbol != instrument.symbol:
                continue
            units = int(float(trade["currentUnits"]))
            inst = instrument or _infer_instrument(symbol)
            position = Position(
                instrument=inst,
                side=Side.BUY if units > 0 else Side.SELL,
                units=abs(units),
                entry_price=float(trade["price"]),
                entry_time=_parse_time(trade["openTime"]),
                stop_price=_nested_price(trade, "stopLossOrder"),
                take_profit_price=_nested_price(trade, "takeProfitOrder"),
                reason=trade.get("clientExtensions", {}).get("comment", ""),
            )
            position.broker_id = trade["id"]  # type: ignore[attr-defined]
            out.append(position)
        return out

    def place_order(self, order: Order) -> Position:
        units = order.units if order.side is Side.BUY else -order.units
        body: Dict[str, Any] = {
            "order": {
                "type": "MARKET",
                "instrument": to_oanda_symbol(order.instrument),
                "units": str(units),
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
            }
        }
        digits = 3 if order.instrument.quote_is_jpy else 5
        if order.stop_price is not None:
            body["order"]["stopLossOnFill"] = {"price": f"{order.stop_price:.{digits}f}"}
        if order.take_profit_price is not None:
            body["order"]["takeProfitOnFill"] = {"price": f"{order.take_profit_price:.{digits}f}"}
        if order.reason:
            body["order"]["clientExtensions"] = {"comment": order.reason[:128]}

        data = self._request("POST", f"/v3/accounts/{self._account}/orders", body)

        fill = data.get("orderFillTransaction")
        if not fill:
            reason = data.get("orderCancelTransaction", {}).get("reason", "不明")
            raise BrokerError(f"注文が約定しなかった: {reason}")

        position = Position(
            instrument=order.instrument,
            side=order.side,
            units=order.units,
            entry_price=float(fill["price"]),
            entry_time=_parse_time(fill["time"]),
            stop_price=order.stop_price,
            take_profit_price=order.take_profit_price,
            reason=order.reason,
        )
        position.broker_id = fill.get("tradeOpened", {}).get("tradeID", "")  # type: ignore[attr-defined]
        log.info("約定: %s %s units @ %s", order.side.value, order.units, position.entry_price)
        return position

    def close_position(self, position: Position, reason: str = "") -> Trade:
        trade_id = getattr(position, "broker_id", "")
        if not trade_id:
            raise BrokerError("建玉IDが不明。get_positions で取得した建玉を渡すこと")
        data = self._request(
            "PUT", f"/v3/accounts/{self._account}/trades/{trade_id}/close", {"units": "ALL"}
        )
        fill = data.get("orderFillTransaction")
        if not fill:
            raise BrokerError(f"決済が成立しなかった: {json.dumps(data)[:300]}")
        closed = fill.get("tradesClosed", [{}])[0]
        return Trade(
            instrument=position.instrument,
            side=position.side,
            units=position.units,
            entry_price=position.entry_price,
            exit_price=float(fill["price"]),
            entry_time=position.entry_time,
            exit_time=_parse_time(fill["time"]),
            pnl=float(closed.get("realizedPL", 0.0)),
            exit_reason=reason,
            entry_reason=position.reason,
        )

    def _fetch_closed_trades(self, count: int = 50) -> List[Dict[str, Any]]:
        query = urllib.parse.urlencode({"state": "CLOSED", "count": count})
        data = self._request("GET", f"/v3/accounts/{self._account}/trades?{query}")
        return data.get("trades", [])

    def poll_closed_trades(self) -> List[Trade]:
        """損切り・利確・ロスカットで決済された取引を回収する。

        こちらから close_position を呼んでいない決済を検知するための経路。
        """
        out: List[Trade] = []
        for raw in self._fetch_closed_trades():
            trade_id = raw["id"]
            if trade_id in self._seen_closed:
                continue
            self._seen_closed.add(trade_id)

            units = int(float(raw.get("initialUnits", 0)))
            if units == 0:
                continue
            symbol = raw["instrument"].replace("_", "/")
            instrument = _infer_instrument(symbol)
            out.append(
                Trade(
                    instrument=instrument,
                    side=Side.BUY if units > 0 else Side.SELL,
                    units=abs(units),
                    entry_price=float(raw["price"]),
                    exit_price=float(raw.get("averageClosePrice", raw["price"])),
                    entry_time=_parse_time(raw["openTime"]),
                    exit_time=_parse_time(raw.get("closeTime", raw["openTime"])),
                    pnl=float(raw.get("realizedPL", 0.0)),
                    exit_reason="業者側決済 (損切り/利確/ロスカット)",
                    entry_reason=raw.get("clientExtensions", {}).get("comment", ""),
                )
            )

        # 記録済みIDが無限に増えないよう、直近ぶんだけ保持する
        if len(self._seen_closed) > 500:
            self._seen_closed = set(list(self._seen_closed)[-250:])
        return out

    # ------------------------------------------------------------------
    def fetch_candles(
        self, instrument: Instrument, granularity: str = "H1", count: int = 500
    ) -> List[Candle]:
        """ヒストリカルデータ取得。バックテスト用データの収集にも使える。"""
        query = urllib.parse.urlencode(
            {"granularity": granularity, "count": min(count, 5000), "price": "M"}
        )
        symbol = to_oanda_symbol(instrument)
        data = self._request("GET", f"/v3/instruments/{symbol}/candles?{query}")
        candles: List[Candle] = []
        for row in data.get("candles", []):
            if not row.get("complete"):
                continue  # 未確定足は使わない
            mid = row["mid"]
            candles.append(
                Candle(
                    time=_parse_time(row["time"]),
                    open=float(mid["o"]),
                    high=float(mid["h"]),
                    low=float(mid["l"]),
                    close=float(mid["c"]),
                    volume=float(row.get("volume", 0)),
                )
            )
        return candles


def _parse_time(value: str) -> datetime:
    # OANDA は 2025-06-10T12:00:00.000000000Z のようなナノ秒精度を返す
    cleaned = value.replace("Z", "+00:00")
    if "." in cleaned:
        head, rest = cleaned.split(".", 1)
        frac, _, tz = rest.partition("+")
        cleaned = f"{head}.{frac[:6]}+{tz}" if tz else f"{head}.{frac[:6]}"
    dt = datetime.fromisoformat(cleaned)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _nested_price(trade: Dict[str, Any], key: str) -> Optional[float]:
    order = trade.get(key)
    return float(order["price"]) if order and "price" in order else None


def _infer_instrument(symbol: str) -> Instrument:
    from ..models import PRESETS

    if symbol in PRESETS:
        return PRESETS[symbol]
    quote = symbol.split("/")[-1]
    is_jpy = quote == "JPY"
    return Instrument(symbol, pip=0.01 if is_jpy else 0.0001, quote_is_jpy=is_jpy)
