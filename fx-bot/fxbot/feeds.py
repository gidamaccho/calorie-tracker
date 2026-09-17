"""価格データの供給源。

CSV / 合成データ / ライブ (ブローカー経由) を同じ形で扱う。
"""

from __future__ import annotations

import csv
import math
import random
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Iterable, Iterator, List, Optional, Sequence

from .models import Candle


class PriceFeed(ABC):
    """足を順に供給する。"""

    @abstractmethod
    def __iter__(self) -> Iterator[Candle]:
        ...


class ListFeed(PriceFeed):
    def __init__(self, candles: Sequence[Candle]) -> None:
        self.candles = list(candles)

    def __iter__(self) -> Iterator[Candle]:
        return iter(self.candles)

    def __len__(self) -> int:
        return len(self.candles)


class CsvFeed(PriceFeed):
    """CSV からローソク足を読む。

    想定する列 (ヘッダ名は大小文字を無視、別名も許容):
      time/date/datetime/timestamp, open, high, low, close, volume(任意)

    時刻は ISO8601 (2025-06-10T12:00:00Z) か 'YYYY-MM-DD HH:MM:SS'、
    もしくは UNIX 秒。タイムゾーンが無い場合は UTC とみなす。
    """

    TIME_KEYS = ("time", "date", "datetime", "timestamp", "日時", "日付")

    def __init__(self, path: str, tz_aware: bool = True) -> None:
        self.path = path
        self.tz_aware = tz_aware
        self._candles: Optional[List[Candle]] = None

    def load(self) -> List[Candle]:
        if self._candles is not None:
            return self._candles

        candles: List[Candle] = []
        with open(self.path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                raise ValueError(f"{self.path}: ヘッダ行が無い")
            norm = {name.strip().lower(): name for name in reader.fieldnames}

            time_key = next((norm[k] for k in self.TIME_KEYS if k in norm), None)
            if time_key is None:
                raise ValueError(
                    f"{self.path}: 時刻列が見つからない (候補: {', '.join(self.TIME_KEYS)})"
                )
            required = {}
            for field in ("open", "high", "low", "close"):
                if field not in norm:
                    raise ValueError(f"{self.path}: '{field}' 列が無い")
                required[field] = norm[field]
            volume_key = norm.get("volume")

            for lineno, row in enumerate(reader, start=2):
                try:
                    candles.append(
                        Candle(
                            time=self._parse_time(row[time_key]),
                            open=float(row[required["open"]]),
                            high=float(row[required["high"]]),
                            low=float(row[required["low"]]),
                            close=float(row[required["close"]]),
                            volume=float(row[volume_key]) if volume_key and row.get(volume_key) else 0.0,
                        )
                    )
                except (ValueError, KeyError, TypeError) as exc:
                    raise ValueError(f"{self.path}:{lineno} 行の読み込みに失敗: {exc}") from exc

        if not candles:
            raise ValueError(f"{self.path}: 有効な足が1本も無い")

        candles.sort(key=lambda c: c.time)
        self._candles = candles
        return candles

    def _parse_time(self, value: str) -> datetime:
        value = value.strip()
        if value.isdigit():
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        cleaned = value.replace("Z", "+00:00").replace("/", "-")
        try:
            dt = datetime.fromisoformat(cleaned)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(cleaned, fmt)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError(f"時刻として解釈できない: {value!r}")
        if dt.tzinfo is None and self.tz_aware:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def __iter__(self) -> Iterator[Candle]:
        return iter(self.load())


class SyntheticFeed(PriceFeed):
    """合成価格データ生成器。

    実データが無いときの動作確認用。幾何ブラウン運動にトレンドの
    切り替わりを加えて、順張り・逆張りどちらの戦略も反応する程度の
    値動きを作る。**成績評価には使わないこと** — 実相場の性質
    (窓、ニュースによる急変、ボラティリティのクラスタリング) を持たない。
    """

    def __init__(
        self,
        bars: int = 2000,
        start_price: float = 150.0,
        annual_volatility: float = 0.09,
        bar_minutes: int = 60,
        start_time: Optional[datetime] = None,
        seed: Optional[int] = 42,
        regime_length: int = 200,
        skip_weekends: bool = True,
    ) -> None:
        self.bars = bars
        self.start_price = start_price
        self.annual_volatility = annual_volatility
        self.bar_minutes = bar_minutes
        self.start_time = start_time or datetime(2024, 1, 1, tzinfo=timezone.utc)
        self.seed = seed
        self.regime_length = regime_length
        self.skip_weekends = skip_weekends

    def __iter__(self) -> Iterator[Candle]:
        rng = random.Random(self.seed)
        bars_per_year = (365 * 24 * 60) / self.bar_minutes
        sigma = self.annual_volatility / math.sqrt(bars_per_year)

        price = self.start_price
        t = self.start_time
        drift = 0.0
        for i in range(self.bars):
            if i % self.regime_length == 0:
                # トレンド局面をときどき切り替える (レンジ/上昇/下降)
                drift = rng.choice([0.0, 1.0, -1.0, 0.5, -0.5]) * sigma * 0.15

            shock = rng.gauss(drift, sigma)
            open_ = price
            close = open_ * math.exp(shock)
            # 足の中の振れ幅。始値終値のレンジより必ず広くする
            wick = abs(rng.gauss(0, sigma)) * open_ * 0.8
            high = max(open_, close) + wick * rng.random()
            low = min(open_, close) - wick * rng.random()

            yield Candle(
                time=t,
                open=round(open_, 3),
                high=round(high, 3),
                low=round(low, 3),
                close=round(close, 3),
                volume=round(rng.uniform(500, 5000)),
            )
            price = close
            t = t + timedelta(minutes=self.bar_minutes)
            if self.skip_weekends:
                while t.weekday() >= 5:
                    t = t + timedelta(days=1)

    def to_list(self) -> List[Candle]:
        return list(self)


def write_csv(candles: Iterable[Candle], path: str) -> int:
    """足を CSV に書き出す。データ収集結果の保存用。"""
    count = 0
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["time", "open", "high", "low", "close", "volume"])
        for c in candles:
            writer.writerow(
                [c.time.isoformat(), c.open, c.high, c.low, c.close, c.volume]
            )
            count += 1
    return count
