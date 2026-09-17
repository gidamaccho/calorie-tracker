"""SBI証券 FX ブラウザ自動操作アダプタ (雛形)。

================== 必ず読むこと ==================
SBI証券は個人向けのFX取引APIを公開していない。したがって「SBI証券で自動売買」を
実現する手段はブラウザ自動操作 (Webスクレイピング) しか無いが、これには以下の
実務上の問題がある。

1. 規約リスク
   証券会社の利用規約は一般に、自動化ツールによるアクセスや画面の機械的操作を
   禁止または制限している。違反した場合、口座凍結・強制解約の可能性がある。
   利用前に必ず自分の口座の規約を確認し、判断は自己責任で行うこと。

2. 技術リスク
   画面構成 (DOM) は予告なく変わる。セレクタが1つ外れただけで
   「発注したつもりが発注されていない」「決済したつもりが建玉が残る」
   といった、資金を直接失う形の故障が起きる。
   API と違って注文の受付確認が構造化されていないため、検証も難しい。

3. 二要素認証・デバイス認証
   ログインフローに追加認証が入ると、無人での連続稼働は成立しない。

このファイルは「動く実装」ではなく「安全側に倒した雛形」である。
  - 既定で dry_run=True。発注メソッドは実際には何も送信せず、内容をログに出すだけ。
  - セレクタは設定ファイルから与える。ハードコードしない (壊れたときに気付けるように)。
  - 認証情報は環境変数からのみ読む。設定ファイルやコードには絶対に書かない。
  - 実発注を有効にするには dry_run=False と confirm_live_trading=True の両方が必要。

実弾で API 経由の自動売買を行いたい場合は、公式APIを提供している業者
(例: OANDA証券の v20 REST API → brokers/oanda.py) を使うほうが安全かつ確実。
==================================================
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..models import Instrument, Order, Position, Tick, Trade, utcnow
from .base import Broker, BrokerError

log = logging.getLogger(__name__)


@dataclass
class SbiWebConfig:
    """SBI Web アダプタの設定。

    selectors には画面上の要素を指す CSS セレクタを入れる。
    実際の値は自分でブラウザの開発者ツールから調べて設定ファイルに書くこと
    (ここに値を同梱すると、画面変更時に「古い値で動いているつもり」になる)。
    """

    login_url: str = "https://www.sbisec.co.jp/ETGate"
    dry_run: bool = True
    confirm_live_trading: bool = False
    headless: bool = True
    timeout_ms: int = 30_000
    # 環境変数名。値そのものではない点に注意。
    username_env: str = "SBI_USERNAME"
    password_env: str = "SBI_PASSWORD"
    trade_password_env: str = "SBI_TRADE_PASSWORD"
    selectors: Dict[str, str] = field(default_factory=dict)
    screenshot_dir: Optional[str] = None  # 失敗時の画面保存先 (調査用)

    REQUIRED_SELECTORS = (
        "username_input",
        "password_input",
        "login_button",
        "fx_menu_link",
        "symbol_selector",
        "units_input",
        "buy_button",
        "sell_button",
        "confirm_button",
        "bid_price",
        "ask_price",
        "equity_value",
        "position_rows",
    )

    def missing_selectors(self) -> List[str]:
        return [k for k in self.REQUIRED_SELECTORS if not self.selectors.get(k)]


class SbiWebBroker(Broker):
    """Playwright でSBI証券の画面を操作するアダプタの雛形。

    実運用に持っていくには、各 _TODO_ メソッドを自分の目で確認した
    画面構造に合わせて実装する必要がある。
    """

    is_live = True

    def __init__(self, config: SbiWebConfig) -> None:
        self.config = config
        self._playwright = None
        self._browser = None
        self._page = None
        self._positions: List[Position] = []

        if not config.dry_run and not config.confirm_live_trading:
            raise BrokerError(
                "実発注を有効にするには confirm_live_trading=True を明示すること。"
                "この設定は『規約を確認し、資金を失うリスクを理解した』という宣言。"
            )
        if not config.dry_run:
            missing = config.missing_selectors()
            if missing:
                raise BrokerError(
                    f"実発注モードだがセレクタ未設定: {', '.join(missing)}。"
                    "未設定のまま動かすと誤発注・決済漏れの原因になる"
                )
            log.warning(
                "SbiWebBroker を実発注モードで初期化した。"
                "少額・単発で必ず手動検証してから連続稼働させること"
            )

    # ------------------------------------------------------------------
    @property
    def dry_run(self) -> bool:
        return self.config.dry_run

    def _credentials(self) -> Dict[str, str]:
        creds = {}
        for key, env in (
            ("username", self.config.username_env),
            ("password", self.config.password_env),
            ("trade_password", self.config.trade_password_env),
        ):
            value = os.environ.get(env)
            if not value and not self.dry_run:
                raise BrokerError(
                    f"環境変数 {env} が未設定。認証情報はコードや設定ファイルではなく"
                    "環境変数 (もしくは OS のキーチェーン) で渡すこと"
                )
            creds[key] = value or ""
        return creds

    def connect(self) -> None:
        if self.dry_run:
            log.info("[DRY-RUN] ログインをスキップ (%s)", self.config.login_url)
            return

        try:
            from playwright.sync_api import sync_playwright  # 実発注時のみ必要
        except ImportError as exc:  # pragma: no cover - 環境依存
            raise BrokerError(
                "playwright が未インストール。`pip install playwright && playwright install chromium`"
            ) from exc

        creds = self._credentials()
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.config.headless)
        self._page = self._browser.new_page()
        self._page.set_default_timeout(self.config.timeout_ms)
        self._login(creds)

    def _login(self, creds: Dict[str, str]) -> None:
        """_TODO_: 実際のログインフローに合わせて実装する。

        実装時の注意:
          - ログイン後に必ず「ログイン済みであることを示す要素」の存在を確認する。
            URLの遷移だけで判断すると、エラー画面を掴んだまま発注しに行く。
          - 追加認証 (デバイス認証・ワンタイムパスワード) が出た場合は、
            黙って続行せず BrokerError で止めること。
        """
        sel = self.config.selectors
        page = self._page
        page.goto(self.config.login_url)
        page.fill(sel["username_input"], creds["username"])
        page.fill(sel["password_input"], creds["password"])
        page.click(sel["login_button"])
        page.wait_for_load_state("networkidle")

        if not page.query_selector(sel["fx_menu_link"]):
            self._screenshot("login_failed")
            raise BrokerError(
                "ログイン後の想定要素が見つからない。追加認証が要求されたか、"
                "画面構成が変わった可能性がある"
            )
        page.click(sel["fx_menu_link"])
        page.wait_for_load_state("networkidle")
        log.info("SBI証券にログインし、FX画面へ遷移した")

    def disconnect(self) -> None:
        for closer in (self._browser, self._playwright):
            if closer is None:
                continue
            try:
                closer.close() if closer is self._browser else closer.stop()
            except Exception as exc:  # pragma: no cover - 終了処理は落とさない
                log.warning("切断時の例外を無視: %s", exc)
        self._browser = self._playwright = self._page = None

    # ------------------------------------------------------------------
    def get_tick(self, instrument: Instrument) -> Tick:
        """_TODO_: 画面から Bid/Ask を読む。

        読み取った値は必ず健全性チェックすること (前回値から極端に乖離していないか、
        Bid < Ask になっているか)。画面のパースミスで桁を1つ間違えると、
        リスク管理の計算がすべて壊れる。
        """
        if self.dry_run:
            raise BrokerError(
                "dry-run では価格取得できない。バックテスト/ペーパーには "
                "PaperBroker + CSV/合成データを使うこと"
            )
        sel = self.config.selectors
        bid = self._parse_price(self._page.inner_text(sel["bid_price"]))
        ask = self._parse_price(self._page.inner_text(sel["ask_price"]))
        if not (0 < bid < ask):
            self._screenshot("bad_tick")
            raise BrokerError(f"価格の読み取りが不正: bid={bid} ask={ask}")
        spread_pips = instrument.price_to_pips(ask - bid)
        if spread_pips > 20:
            raise BrokerError(f"スプレッドが異常 ({spread_pips:.1f} pips)。読み取りミスを疑う")
        return Tick(time=utcnow(), bid=bid, ask=ask)

    @staticmethod
    def _parse_price(text: str) -> float:
        cleaned = text.strip().replace(",", "").replace("円", "")
        try:
            return float(cleaned)
        except ValueError as exc:
            raise BrokerError(f"価格として解釈できない文字列: {text!r}") from exc

    def get_equity(self) -> float:
        """_TODO_: 有効証拠金を画面から読む。"""
        if self.dry_run:
            return 0.0
        return self._parse_price(self._page.inner_text(self.config.selectors["equity_value"]))

    def get_positions(self, instrument: Optional[Instrument] = None) -> List[Position]:
        """_TODO_: 建玉一覧を画面から読む。

        ローカルの self._positions を正とせず、必ず画面側を正とすること。
        手動決済やロスカットでズレる。
        """
        if self.dry_run:
            return list(self._positions)
        raise NotImplementedError(
            "建玉一覧のパースは未実装。position_rows セレクタを使って実装すること"
        )

    def place_order(self, order: Order) -> Position:
        """_TODO_: 発注する。

        実装時の必須事項:
          - 発注後に注文受付画面/約定履歴を読み、実際に通ったことを確認する。
            確認できない場合は「約定したかも知れない」状態なので、
            リトライせずに BrokerError で止めて人間に引き継ぐこと。
            二重発注は資金を最も速く失うバグ。
          - 数量の単位 (通貨単位 or 万通貨) を画面表記と必ず突き合わせる。
        """
        if self.dry_run:
            log.info(
                "[DRY-RUN] 発注: %s %s %s units @ market / SL=%s TP=%s (%s)",
                order.instrument.symbol,
                order.side.value,
                order.units,
                order.stop_price,
                order.take_profit_price,
                order.reason,
            )
            position = Position(
                instrument=order.instrument,
                side=order.side,
                units=order.units,
                entry_price=0.0,
                entry_time=utcnow(),
                stop_price=order.stop_price,
                take_profit_price=order.take_profit_price,
                reason=order.reason,
            )
            self._positions.append(position)
            return position

        raise NotImplementedError(
            "実発注フローは未実装。SbiWebConfig.selectors を設定のうえ、"
            "この関数に発注操作と『約定確認』を実装すること"
        )

    def close_position(self, position: Position, reason: str = "") -> Trade:
        """_TODO_: 決済する。

        決済は発注以上に失敗が許されない。決済操作後、建玉一覧を読み直して
        当該建玉が消えたことを確認するまで成功扱いにしないこと。
        """
        if self.dry_run:
            log.info("[DRY-RUN] 決済: %s %s units (%s)",
                     position.instrument.symbol, position.units, reason)
            if position in self._positions:
                self._positions.remove(position)
            return Trade(
                instrument=position.instrument,
                side=position.side,
                units=position.units,
                entry_price=position.entry_price,
                exit_price=position.entry_price,
                entry_time=position.entry_time,
                exit_time=utcnow(),
                pnl=0.0,
                exit_reason=f"[DRY-RUN] {reason}",
                entry_reason=position.reason,
            )
        raise NotImplementedError("実決済フローは未実装")

    def _screenshot(self, tag: str) -> None:
        if not (self.config.screenshot_dir and self._page):
            return
        os.makedirs(self.config.screenshot_dir, exist_ok=True)
        path = os.path.join(
            self.config.screenshot_dir, f"{tag}_{utcnow():%Y%m%d_%H%M%S}.png"
        )
        try:
            self._page.screenshot(path=path, full_page=True)
            log.info("画面を保存した: %s", path)
        except Exception as exc:  # pragma: no cover
            log.warning("スクリーンショット保存に失敗: %s", exc)
