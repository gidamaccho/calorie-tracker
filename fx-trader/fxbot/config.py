"""設定ファイル(YAML)の読み込み。"""
from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml


@dataclass
class StrategyConfig:
    name: str = "ma_cross"
    params: dict = field(default_factory=dict)


@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 1.0  # 1 トレードで失ってよい資金の割合(%)
    sl_atr_mult: float = 2.0  # 損切り幅 = ATR × この倍率
    tp_atr_mult: float = 3.0  # 利確幅 = ATR × この倍率
    atr_period: int = 14
    max_daily_loss_pct: float = 3.0  # 1 日でこれ以上減ったら新規停止(0 で無効)
    max_spread_pips: float = 3.0  # ライブ時、スプレッドがこれより広ければ見送り


@dataclass
class BacktestConfig:
    initial_balance: float = 1_000_000
    spread_pips: float = 0.3
    contract_size: float = 100_000  # 1 ロットの通貨数
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lot: float = 50.0
    # 決済通貨(USDJPY なら JPY)→ 口座通貨の換算レート。JPY 口座で USDJPY なら 1.0
    quote_to_account_rate: float = 1.0


@dataclass
class LiveConfig:
    magic: int = 20261018  # このボットの注文を識別する番号
    poll_seconds: float = 10
    history_bars: int = 500
    deviation_points: int = 20  # 許容スリッページ(ポイント)
    dry_run: bool = False  # True なら発注せずログだけ出す
    # 本番(リアル)口座での取引を許可するか。True に加えて環境変数
    # FXBOT_ALLOW_LIVE=yes が無いと、リアル口座では起動を拒否する。
    allow_live_account: bool = False
    terminal_path: str | None = None  # MT5 terminal64.exe のパス(通常は不要)


@dataclass
class Config:
    symbol: str = "USDJPY"
    timeframe: str = "H1"
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    live: LiveConfig = field(default_factory=LiveConfig)


def _build(cls, data: dict | None):
    data = data or {}
    known = {f.name for f in fields(cls)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"{cls.__name__} に不明な設定項目: {', '.join(sorted(unknown))}")
    return cls(**data)


def load_config(path: str | Path | None) -> Config:
    if path is None:
        return Config()
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    sections = {"strategy": StrategyConfig, "risk": RiskConfig, "backtest": BacktestConfig, "live": LiveConfig}
    for key, cls in sections.items():
        raw[key] = _build(cls, raw.get(key))
    return _build(Config, raw)
