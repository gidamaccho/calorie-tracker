"""MetaTrader 5 との接続。

MetaTrader5 パッケージは Windows 版のみ。MT5 ターミナルを起動・ログインした状態で使う。
"""
from dataclasses import dataclass

import pandas as pd


@dataclass
class Position:
    ticket: int
    direction: int  # 1 = 買い, -1 = 売り
    volume: float
    price_open: float


@dataclass
class SymbolSpec:
    point: float
    digits: int
    volume_min: float
    volume_max: float
    volume_step: float
    value_per_price_per_lot: float  # 価格が 1.0 動いたときの 1 ロットの損益(口座通貨)


class MT5Broker:
    def __init__(self, mt5_module=None):
        if mt5_module is None:
            try:
                import MetaTrader5 as mt5_module  # type: ignore
            except ImportError as e:
                raise RuntimeError(
                    "MetaTrader5 パッケージが見つかりません。Windows で `pip install MetaTrader5` してください。"
                ) from e
        self.mt5 = mt5_module

    # --- 接続 ---
    def connect(self, login: int | None = None, password: str | None = None,
                server: str | None = None, path: str | None = None) -> None:
        kwargs = {}
        if path:
            kwargs["path"] = path
        if login:
            kwargs.update(login=int(login), password=password or "", server=server or "")
        if not self.mt5.initialize(**kwargs):
            raise RuntimeError(f"MT5 に接続できません: {self.mt5.last_error()}")

    def shutdown(self) -> None:
        self.mt5.shutdown()

    def is_demo(self) -> bool:
        info = self._account()
        return info.trade_mode == self.mt5.ACCOUNT_TRADE_MODE_DEMO

    def account_summary(self) -> str:
        info = self._account()
        kind = "デモ" if self.is_demo() else "リアル"
        return f"口座 {info.login} ({kind}) / {info.server} / 残高 {info.balance} {info.currency}"

    def equity(self) -> float:
        return float(self._account().equity)

    def _account(self):
        info = self.mt5.account_info()
        if info is None:
            raise RuntimeError(f"口座情報を取得できません: {self.mt5.last_error()}")
        return info

    # --- 銘柄・価格 ---
    def symbol_spec(self, symbol: str) -> SymbolSpec:
        if not self.mt5.symbol_select(symbol, True):
            raise RuntimeError(f"銘柄 {symbol} を選択できません")
        s = self.mt5.symbol_info(symbol)
        return SymbolSpec(
            point=s.point, digits=s.digits,
            volume_min=s.volume_min, volume_max=s.volume_max, volume_step=s.volume_step,
            value_per_price_per_lot=s.trade_tick_value / s.trade_tick_size,
        )

    def bid_ask(self, symbol: str) -> tuple[float, float]:
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"{symbol} の価格を取得できません")
        return tick.bid, tick.ask

    def closed_bars(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        """確定済みの足だけを返す(位置 0 = 形成中の足は除外)。"""
        tf = getattr(self.mt5, f"TIMEFRAME_{timeframe.upper()}", None)
        if tf is None:
            raise ValueError(f"不明な時間足: {timeframe}(例: M1, M5, M15, H1, H4, D1)")
        rates = self.mt5.copy_rates_from_pos(symbol, tf, 1, count)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"{symbol} の足データを取得できません: {self.mt5.last_error()}")
        df = pd.DataFrame(rates)
        df.index = pd.to_datetime(df["time"], unit="s")
        df.index.name = "time"
        return df[["open", "high", "low", "close"]].astype(float)

    # --- ポジション・注文 ---
    def position(self, symbol: str, magic: int) -> Position | None:
        for p in self.mt5.positions_get(symbol=symbol) or []:
            if p.magic == magic:
                direction = 1 if p.type == self.mt5.POSITION_TYPE_BUY else -1
                return Position(p.ticket, direction, p.volume, p.price_open)
        return None

    def open(self, symbol: str, direction: int, lots: float, sl: float, tp: float,
             magic: int, deviation: int, comment: str = "fxbot") -> None:
        bid, ask = self.bid_ask(symbol)
        self._send({
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lots,
            "type": self.mt5.ORDER_TYPE_BUY if direction == 1 else self.mt5.ORDER_TYPE_SELL,
            "price": ask if direction == 1 else bid,
            "sl": sl,
            "tp": tp,
            "deviation": deviation,
            "magic": magic,
            "comment": comment,
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self._filling(symbol),
        })

    def close(self, symbol: str, pos: Position, magic: int, deviation: int) -> None:
        bid, ask = self.bid_ask(symbol)
        self._send({
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": pos.volume,
            "type": self.mt5.ORDER_TYPE_SELL if pos.direction == 1 else self.mt5.ORDER_TYPE_BUY,
            "position": pos.ticket,
            "price": bid if pos.direction == 1 else ask,
            "deviation": deviation,
            "magic": magic,
            "comment": "fxbot close",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self._filling(symbol),
        })

    def _filling(self, symbol: str) -> int:
        mode = self.mt5.symbol_info(symbol).filling_mode
        if mode & 1:
            return self.mt5.ORDER_FILLING_FOK
        if mode & 2:
            return self.mt5.ORDER_FILLING_IOC
        return self.mt5.ORDER_FILLING_RETURN

    def _send(self, request: dict) -> None:
        result = self.mt5.order_send(request)
        if result is None or result.retcode != self.mt5.TRADE_RETCODE_DONE:
            detail = self.mt5.last_error() if result is None else f"retcode={result.retcode} {result.comment}"
            raise RuntimeError(f"注文が失敗しました: {detail}")
