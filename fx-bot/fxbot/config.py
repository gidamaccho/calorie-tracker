"""設定ファイルの読み込み。

JSON を標準とする (標準ライブラリだけで読めるため)。
PyYAML が入っていれば .yml / .yaml も読める。

認証情報はここに書かない。必ず環境変数で渡すこと。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from typing import Any, Dict, Optional

from .engine import EngineConfig
from .models import PRESETS, Instrument
from .risk import RiskConfig


@dataclass
class AppConfig:
    symbol: str = "USD/JPY"
    instrument_overrides: Dict[str, Any] = field(default_factory=dict)
    strategy: str = "sma_cross"
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    broker: str = "paper"
    broker_params: Dict[str, Any] = field(default_factory=dict)
    risk: Dict[str, Any] = field(default_factory=dict)
    engine: Dict[str, Any] = field(default_factory=dict)
    starting_balance: float = 1_000_000.0
    spread_pips: float = 0.4
    slippage_pips: float = 0.2
    commission_per_10k: float = 0.0
    swap_per_10k_per_day: float = 0.0
    data_csv: Optional[str] = None
    journal_dir: str = "./journal"
    journal_enabled: bool = True
    log_level: str = "INFO"
    log_file: Optional[str] = None

    # ------------------------------------------------------------------
    def instrument(self) -> Instrument:
        base = PRESETS.get(self.symbol)
        if base is None:
            quote = self.symbol.split("/")[-1].upper()
            is_jpy = quote == "JPY"
            base = Instrument(
                self.symbol,
                pip=0.01 if is_jpy else 0.0001,
                quote_is_jpy=is_jpy,
            )
        if not self.instrument_overrides:
            return base
        valid = {f.name for f in fields(Instrument)}
        unknown = set(self.instrument_overrides) - valid
        if unknown:
            raise ValueError(f"instrument_overrides の未知のキー: {', '.join(sorted(unknown))}")
        merged = {f.name: getattr(base, f.name) for f in fields(Instrument)}
        merged.update(self.instrument_overrides)
        return Instrument(**merged)

    def risk_config(self) -> RiskConfig:
        data = dict(self.risk)
        hours = data.get("trading_hours")
        if isinstance(hours, list):
            data["trading_hours"] = tuple(hours)
        valid = {f.name for f in fields(RiskConfig)}
        unknown = set(data) - valid
        if unknown:
            raise ValueError(
                f"risk の未知のキー: {', '.join(sorted(unknown))}。"
                f"有効なキー: {', '.join(sorted(valid))}"
            )
        return RiskConfig(**data)

    def engine_config(self) -> EngineConfig:
        valid = {f.name for f in fields(EngineConfig)}
        unknown = set(self.engine) - valid
        if unknown:
            raise ValueError(f"engine の未知のキー: {', '.join(sorted(unknown))}")
        return EngineConfig(**self.engine)


def load_config(path: Optional[str]) -> AppConfig:
    if not path:
        return AppConfig()
    if not os.path.exists(path):
        raise FileNotFoundError(f"設定ファイルが無い: {path}")

    raw = _read_structured(path)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: トップレベルはオブジェクトである必要がある")

    # JSON にはコメント構文が無いので、"_" で始まるキーを注記として扱い無視する。
    raw = {k: v for k, v in raw.items() if not str(k).startswith("_")}

    valid = {f.name for f in fields(AppConfig)}
    unknown = set(raw) - valid
    if unknown:
        raise ValueError(
            f"{path}: 未知の設定キー: {', '.join(sorted(unknown))}。"
            f"有効なキー: {', '.join(sorted(valid))}"
        )
    config = AppConfig(**raw)
    _warn_on_embedded_secrets(raw, path)
    return config


def _read_structured(path: str) -> Any:
    text = open(path, encoding="utf-8").read()
    if path.endswith((".yml", ".yaml")):
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "YAML を読むには PyYAML が必要 (`pip install pyyaml`)。"
                "または設定を .json で書くこと"
            ) from exc
        return yaml.safe_load(text)
    return json.loads(text)


SECRET_HINTS = ("password", "secret", "token", "apikey", "api_key", "パスワード")

#: 値が「秘密そのもの」ではないと分かっているキーの語尾。
#: 例: password_input は入力欄を指すCSSセレクタ名、password_env は環境変数名。
SECRET_EXEMPT_SUFFIXES = ("_env", "_input", "_selector", "_field", "_button", "_label")

#: この名前のサブツリーは丸ごと対象外にする (中身がCSSセレクタなど)。
SECRET_EXEMPT_SECTIONS = ("selectors",)


def _warn_on_embedded_secrets(raw: Dict[str, Any], path: str) -> None:
    """設定ファイルに認証情報らしき値が直書きされていないか確認する。

    値ではなく「値の置き場所」を指すキー (環境変数名、CSSセレクタ名) は除外する。
    """
    found = []

    def walk(node: Any, trail: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = str(key).lower()
                if lowered in SECRET_EXEMPT_SECTIONS:
                    continue
                if lowered.endswith(SECRET_EXEMPT_SUFFIXES):
                    continue
                if any(h in lowered for h in SECRET_HINTS) and isinstance(value, str) and value:
                    found.append(f"{trail}{key}")
                walk(value, f"{trail}{key}.")
        elif isinstance(node, list):
            for item in node:
                walk(item, trail)

    walk(raw, "")
    if found:
        raise ValueError(
            f"{path}: 認証情報を設定ファイルに書かないこと ({', '.join(found)})。"
            "環境変数で渡し、ファイルには環境変数名だけを書く"
        )
