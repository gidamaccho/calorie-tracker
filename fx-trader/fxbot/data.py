"""価格データの読み込み・生成。

DataFrame の形式: index = 足の開始時刻(DatetimeIndex)、列 = open/high/low/close(Bid 価格)
"""
import numpy as np
import pandas as pd

REQUIRED = ["open", "high", "low", "close"]


def load_csv(path: str) -> pd.DataFrame:
    """CSV を読み込む。

    対応形式:
      - time,open,high,low,close[,volume] の一般的な CSV
      - MT5 の「エクスポート」で出したタブ区切り(<DATE> <TIME> <OPEN> ...)
    """
    df = pd.read_csv(path, sep=None, engine="python")
    df.columns = [str(c).strip().strip("<>").lower() for c in df.columns]

    if "date" in df.columns and "time" in df.columns:
        stamp = df["date"].astype(str).str.replace(".", "-", regex=False) + " " + df["time"].astype(str)
    else:
        col = next((c for c in ("time", "datetime", "date", "timestamp") if c in df.columns), None)
        if col is None:
            raise ValueError("時刻の列(time / datetime / date)が見つかりません")
        stamp = df[col].astype(str).str.replace(".", "-", regex=False)

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"必要な列がありません: {', '.join(missing)}")

    out = df[REQUIRED].astype(float)
    out.index = pd.to_datetime(stamp)
    out.index.name = "time"
    return out.sort_index()


def synthetic_ohlc(bars: int = 5000, start_price: float = 150.0, seed: int = 0, freq: str = "h") -> pd.DataFrame:
    """動作確認用のランダムな価格データ(トレンド局面とレンジ局面が混ざる)。"""
    rng = np.random.default_rng(seed)
    vol = 0.0015
    # 数百本ごとにドリフト(トレンド)が切り替わる
    regime_len = 300
    drifts = rng.normal(0, 0.0004, size=bars // regime_len + 1).repeat(regime_len)[:bars]
    rets = drifts + rng.normal(0, vol, size=bars)
    close = start_price * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[start_price], close[:-1]])
    wiggle = np.abs(rng.normal(0, vol * 0.6, size=(2, bars))) * close
    high = np.maximum(open_, close) + wiggle[0]
    low = np.minimum(open_, close) - wiggle[1]
    idx = pd.date_range("2024-01-01", periods=bars, freq=freq, name="time")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)
