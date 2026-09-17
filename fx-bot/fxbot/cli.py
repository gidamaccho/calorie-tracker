"""コマンドラインインターフェース。

  python -m fxbot backtest --config examples/config.json
  python -m fxbot paper    --config examples/config.json
  python -m fxbot live     --config examples/live_oanda.json --i-understand-the-risks
  python -m fxbot optimize --config examples/config.json --param fast=10,20,30
  python -m fxbot fetch    --symbol USD/JPY --granularity H1 --out data/usdjpy_h1.csv
"""

from __future__ import annotations

import argparse
import itertools
import logging
import sys
from typing import Dict, List, Optional, Sequence

from .backtest import run_backtest
from .brokers import build_broker
from .brokers.base import BrokerError
from .config import AppConfig, load_config
from .engine import TradingEngine
from .feeds import CsvFeed, SyntheticFeed, write_csv
from .journal import Journal, setup_logging
from .models import Candle
from .pricesource import LiveQuoteSource, ReplayQuoteSource
from .strategies import REGISTRY, build_strategy

log = logging.getLogger("fxbot")


def _load_candles(config: AppConfig, args) -> List[Candle]:
    if args.csv or config.data_csv:
        path = args.csv or config.data_csv
        candles = CsvFeed(path).load()
        log.info("%s から %d 本読み込んだ", path, len(candles))
        return candles

    log.warning(
        "価格データが指定されていないので合成データを使う。"
        "これは配管の動作確認用であり、成績は一切あてにならない。"
        "実データを --csv で渡すこと"
    )
    return SyntheticFeed(bars=args.bars, seed=args.seed).to_list()


def cmd_backtest(args) -> int:
    config = load_config(args.config)
    setup_logging(args.log_level or config.log_level)
    candles = _load_candles(config, args)
    instrument = config.instrument()

    strategy = build_strategy(
        args.strategy or config.strategy, instrument, config.strategy_params
    )
    if len(candles) < strategy.warmup + 10:
        log.error(
            "足が足りない: %d 本しかないが、この戦略は最低 %d 本必要",
            len(candles), strategy.warmup + 10,
        )
        return 1

    result = run_backtest(
        candles=candles,
        strategy=strategy,
        instrument=instrument,
        risk_config=config.risk_config(),
        starting_balance=config.starting_balance,
        spread_pips=config.spread_pips,
        slippage_pips=config.slippage_pips,
        commission_per_10k=config.commission_per_10k,
        swap_per_10k_per_day=config.swap_per_10k_per_day,
    )
    print(result.summary())
    if args.trades:
        print()
        print(result.trade_table(limit=args.trades))
    if args.export:
        journal = Journal(args.export)
        for trade in result.trades:
            journal.record_trade(trade)
        print(f"\nトレード記録を書き出した: {journal.trades_path}")
    return 0


def cmd_optimize(args) -> int:
    """パラメータの総当たり検証。

    注意: ここで見つかる「最良のパラメータ」は、その期間に最も都合よく
    当てはまった値でしかない。実運用の成績を保証しない。
    採用するなら、検証していない別期間 (アウトオブサンプル) で必ず確認すること。
    """
    config = load_config(args.config)
    setup_logging(args.log_level or "WARNING")
    candles = _load_candles(config, args)
    instrument = config.instrument()
    name = args.strategy or config.strategy

    grid: Dict[str, List] = {}
    for spec in args.param:
        if "=" not in spec:
            log.error("--param は name=v1,v2,v3 の形式で指定する: %r", spec)
            return 1
        key, values = spec.split("=", 1)
        grid[key.strip()] = [_coerce(v) for v in values.split(",")]

    if not grid:
        log.error("--param が1つも指定されていない")
        return 1

    keys = list(grid)
    combos = list(itertools.product(*(grid[k] for k in keys)))
    print(f"{len(combos)} 通りを検証する ({name} / {instrument.symbol} / {len(candles)}本)\n")

    rows = []
    for combo in combos:
        params = dict(config.strategy_params)
        params.update(dict(zip(keys, combo)))
        try:
            strategy = build_strategy(name, instrument, params)
            result = run_backtest(
                candles=candles,
                strategy=strategy,
                instrument=instrument,
                risk_config=config.risk_config(),
                starting_balance=config.starting_balance,
                spread_pips=config.spread_pips,
                slippage_pips=config.slippage_pips,
            )
        except (ValueError, KeyError) as exc:
            log.warning("スキップ %s: %s", dict(zip(keys, combo)), exc)
            continue
        rows.append((dict(zip(keys, combo)), result))

    if not rows:
        print("有効な組み合わせが無かった")
        return 1

    rows.sort(key=lambda r: r[1].net_pnl, reverse=True)
    header = f"{'パラメータ':<34} {'損益(円)':>12} {'PF':>6} {'勝率':>7} {'取引':>5} {'最大DD':>8}"
    print(header)
    print("-" * len(header))
    for params, result in rows[: args.top]:
        pf = result.profit_factor
        pf_text = "inf" if pf == float("inf") else f"{pf:.2f}"
        label = ", ".join(f"{k}={v}" for k, v in params.items())
        print(
            f"{label:<34} {result.net_pnl:>12,.0f} {pf_text:>6} "
            f"{result.win_rate:>6.1f}% {result.total_trades:>5} "
            f"{result.max_drawdown * 100:>7.2f}%"
        )
    print(
        "\n⚠ 上位の値は、この期間に過剰適合している可能性が高い。"
        "\n  別期間のデータで再検証してから使うこと。"
    )
    return 0


def _coerce(text: str):
    text = text.strip()
    for caster in (int, float):
        try:
            return caster(text)
        except ValueError:
            continue
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    return text


def cmd_run(args, live: bool) -> int:
    config = load_config(args.config)
    setup_logging(args.log_level or config.log_level, config.log_file)
    instrument = config.instrument()

    try:
        broker = (
            _build_live_broker(config, args)
            if live
            else _build_paper_broker(config, args)
        )
    except (BrokerError, KeyError, ValueError, FileNotFoundError) as exc:
        log.error("ブローカーの初期化に失敗: %s", exc)
        return 1

    if broker.is_live and not args.i_understand_the_risks:
        print(
            "\n実弾モードで起動しようとしている。\n"
            "  - 自動売買は、バグ・通信断・想定外の相場で資金を失う。\n"
            "  - まず paper モードとデモ口座で、月単位で検証すること。\n"
            "  - 続行するには --i-understand-the-risks を付ける。\n",
            file=sys.stderr,
        )
        return 2

    strategy = build_strategy(args.strategy or config.strategy, instrument, config.strategy_params)

    warmup: Optional[List[Candle]] = None
    if live and (args.csv or config.data_csv):
        path = args.csv or config.data_csv
        warmup = CsvFeed(path).load()[-strategy.warmup * 2 :]
    elif hasattr(broker, "fetch_candles"):
        try:
            broker.connect()
            warmup = broker.fetch_candles(
                instrument,
                granularity=args.granularity,
                count=strategy.warmup * 2,
            )
        except BrokerError as exc:
            log.warning("過去足の取得に失敗したので warmup 無しで開始する: %s", exc)

    engine_config = config.engine_config()
    # 保存済みの足を再生する場合、実時間で待つ意味は無いので全速で回す。
    if isinstance(getattr(broker, "price_source", None), ReplayQuoteSource):
        engine_config.poll_seconds = 0.0
        log.info("再生モードのため待ち時間なしで実行する")

    engine = TradingEngine(
        broker=broker,
        strategy=strategy,
        instrument=instrument,
        risk_config=config.risk_config(),
        engine_config=engine_config,
        journal=Journal(config.journal_dir, config.journal_enabled),
        warmup_candles=warmup,
    )
    try:
        engine.run()
    except BrokerError as exc:
        log.critical("致命的なブローカーエラー: %s", exc)
        return 1
    return 0


def _build_live_broker(config: AppConfig, args):
    """実弾用ブローカーを組み立てる。"""
    name = args.broker or config.broker
    if name == "paper":
        raise ValueError(
            "live モードで broker='paper' が指定されている。"
            "実弾で動かすなら oanda か sbi_web を設定すること"
        )
    return build_broker(name, dict(config.broker_params))


def _build_paper_broker(config: AppConfig, args):
    """ペーパートレード用ブローカーを組み立てる。

    約定は常に模擬だが、価格は次の優先順位で決める:
      1. --csv / data_csv があれば、その足を再生する (オフライン)
      2. 設定の broker が実ブローカーなら、その気配値を使う (発注はしない)
      3. どちらも無ければ合成データを再生する (配管確認のみ)
    """
    csv_path = args.csv or config.data_csv
    quote_broker = args.broker or config.broker

    if csv_path:
        candles = CsvFeed(csv_path).load()
        source = ReplayQuoteSource(candles, spread_pips=config.spread_pips)
        log.info("価格: %s を再生する (%d本)", csv_path, len(candles))
    elif quote_broker and quote_broker != "paper":
        source = LiveQuoteSource(build_broker(quote_broker, dict(config.broker_params)))
        log.info("価格: %s の気配値を使う。発注は模擬のみ", quote_broker)
    else:
        log.warning(
            "価格データが指定されていないので合成データを再生する。"
            "配管の確認にはなるが、成績には意味が無い。"
            "--csv で実データを渡すか、設定で実ブローカーを指定すること"
        )
        source = ReplayQuoteSource(
            SyntheticFeed(bars=args.bars, seed=args.seed).to_list(),
            spread_pips=config.spread_pips,
        )

    from .brokers.paper import PaperBroker

    return PaperBroker(
        starting_balance=config.starting_balance,
        spread_pips=config.spread_pips,
        slippage_pips=config.slippage_pips,
        commission_per_10k=config.commission_per_10k,
        swap_per_10k_per_day=config.swap_per_10k_per_day,
        price_source=source,
    )


def cmd_fetch(args) -> int:
    """OANDA からヒストリカルデータを取得して CSV に保存する。"""
    setup_logging(args.log_level or "INFO")
    config = load_config(args.config)
    instrument = config.instrument() if not args.symbol else _instrument_from_symbol(args.symbol)

    if args.synthetic:
        candles = SyntheticFeed(bars=args.bars, seed=args.seed).to_list()
        log.warning("合成データを生成した。実相場の代わりにはならない")
    else:
        try:
            broker = build_broker("oanda", dict(config.broker_params))
            broker.connect()
            candles = broker.fetch_candles(instrument, args.granularity, args.bars)
        except (BrokerError, KeyError) as exc:
            log.error("取得に失敗: %s", exc)
            log.info("環境変数 OANDA_TOKEN / OANDA_ACCOUNT_ID を設定するか、"
                     "--synthetic で合成データを生成すること")
            return 1

    count = write_csv(candles, args.out)
    print(f"{count} 本を {args.out} に保存した")
    return 0


def _instrument_from_symbol(symbol: str):
    from .models import PRESETS, Instrument

    if symbol in PRESETS:
        return PRESETS[symbol]
    is_jpy = symbol.split("/")[-1].upper() == "JPY"
    return Instrument(symbol, pip=0.01 if is_jpy else 0.0001, quote_is_jpy=is_jpy)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fxbot",
        description="FX自動売買フレームワーク (バックテスト / ペーパー / ライブ)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "戦略: " + ", ".join(sorted(REGISTRY)) + "\n"
            "まず backtest と paper で十分に検証してから live を使うこと。"
        ),
    )
    parser.add_argument("--log-level", help="DEBUG/INFO/WARNING/ERROR")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_log_level(p):
        p.add_argument(
            "--log-level", default=argparse.SUPPRESS, help="DEBUG/INFO/WARNING/ERROR"
        )

    def add_common(p):
        add_log_level(p)
        p.add_argument("--config", "-c", help="設定ファイル (.json / .yml)")
        p.add_argument("--strategy", "-s", choices=sorted(REGISTRY), help="戦略名")
        p.add_argument("--csv", help="価格データCSV")
        p.add_argument("--bars", type=int, default=5000, help="合成データの本数")
        p.add_argument("--seed", type=int, default=42, help="合成データの乱数シード")

    p_bt = sub.add_parser("backtest", help="ヒストリカルデータで検証する")
    add_common(p_bt)
    p_bt.add_argument("--trades", type=int, default=0, help="トレード明細をN件表示")
    p_bt.add_argument("--export", help="トレード記録の出力ディレクトリ")
    p_bt.set_defaults(func=cmd_backtest)

    p_opt = sub.add_parser("optimize", help="パラメータを総当たりで検証する")
    add_common(p_opt)
    p_opt.add_argument("--param", "-p", action="append", default=[],
                       help="name=v1,v2,v3 の形式。複数指定可")
    p_opt.add_argument("--top", type=int, default=15, help="上位N件を表示")
    p_opt.set_defaults(func=cmd_optimize)

    p_paper = sub.add_parser("paper", help="実弾を使わずリアルタイム稼働する")
    add_common(p_paper)
    p_paper.add_argument("--broker", help="使用するブローカー (既定: paper)")
    p_paper.add_argument("--granularity", default="H1", help="warmup足の時間足")
    p_paper.add_argument("--i-understand-the-risks", action="store_true",
                         help=argparse.SUPPRESS)
    p_paper.set_defaults(func=lambda a: cmd_run(a, live=False))

    p_live = sub.add_parser("live", help="実弾で稼働する (要確認フラグ)")
    add_common(p_live)
    p_live.add_argument("--broker", help="使用するブローカー")
    p_live.add_argument("--granularity", default="H1", help="warmup足の時間足")
    p_live.add_argument("--i-understand-the-risks", action="store_true",
                        help="実弾取引のリスクを理解したうえで実行する")
    p_live.set_defaults(func=lambda a: cmd_run(a, live=True))

    p_fetch = sub.add_parser("fetch", help="価格データを取得してCSV保存する")
    add_log_level(p_fetch)
    p_fetch.add_argument("--config", "-c", help="設定ファイル")
    p_fetch.add_argument("--symbol", help="通貨ペア (例: USD/JPY)")
    p_fetch.add_argument("--granularity", default="H1", help="M1/M5/M15/H1/H4/D")
    p_fetch.add_argument("--bars", type=int, default=2000, help="取得本数")
    p_fetch.add_argument("--seed", type=int, default=42)
    p_fetch.add_argument("--synthetic", action="store_true",
                         help="API接続せず合成データを生成する")
    p_fetch.add_argument("--out", "-o", required=True, help="出力先CSV")
    p_fetch.set_defaults(func=cmd_fetch)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "log_level"):
        args.log_level = None
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n中断した", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
