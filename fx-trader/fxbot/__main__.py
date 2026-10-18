"""コマンドライン: python -m fxbot <backtest|fetch|live|strategies> ..."""
import argparse
import logging
import os
import sys
from pathlib import Path

from .backtest import run_backtest
from .config import load_config
from .data import load_csv, synthetic_ohlc
from .strategies import STRATEGIES, create_strategy


def _connect_mt5(cfg):
    from .broker import MT5Broker

    broker = MT5Broker()
    broker.connect(
        login=os.environ.get("MT5_LOGIN"),
        password=os.environ.get("MT5_PASSWORD"),
        server=os.environ.get("MT5_SERVER"),
        path=cfg.live.terminal_path,
    )
    return broker


def cmd_backtest(args, cfg):
    if args.csv:
        df = load_csv(args.csv)
    elif args.mt5:
        broker = _connect_mt5(cfg)
        try:
            df = broker.closed_bars(cfg.symbol, cfg.timeframe, args.mt5)
        finally:
            broker.shutdown()
    else:
        print(f"※ データ指定が無いのでランダム生成データ {args.synthetic} 本で実行します(動作確認用)\n")
        df = synthetic_ohlc(args.synthetic)

    names = list(STRATEGIES) if args.strategy == "all" else [args.strategy or cfg.strategy.name]
    print(f"{cfg.symbol} {cfg.timeframe}  {df.index[0]} 〜 {df.index[-1]}  ({len(df)} 本)\n")
    for name in names:
        params = cfg.strategy.params if name == cfg.strategy.name else {}
        strategy = create_strategy(name, params)
        result = run_backtest(df, strategy, cfg.risk, cfg.backtest, cfg.symbol)
        print(f"=== {strategy} ===")
        for k, v in result.stats.items():
            print(f"  {k:<14} {v:,}" if isinstance(v, (int, float)) else f"  {k:<14} {v}")
        print()
        if args.trades_out:
            out = Path(args.trades_out)
            if len(names) > 1:
                out = out.with_name(f"{out.stem}_{name}{out.suffix}")
            result.trades_frame().to_csv(out, index=False)
            print(f"  取引履歴を {out} に保存しました\n")


def cmd_fetch(args, cfg):
    broker = _connect_mt5(cfg)
    try:
        df = broker.closed_bars(cfg.symbol, cfg.timeframe, args.bars)
    finally:
        broker.shutdown()
    df.to_csv(args.out)
    print(f"{len(df)} 本を {args.out} に保存しました")


def cmd_live(args, cfg):
    from .live import Trader

    if args.dry_run:
        cfg.live.dry_run = True
    Path("logs").mkdir(exist_ok=True)
    logging.getLogger().addHandler(logging.FileHandler("logs/fxbot.log", encoding="utf-8"))
    for h in logging.getLogger().handlers:
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    broker = _connect_mt5(cfg)
    try:
        Trader(broker, create_strategy(cfg.strategy.name, cfg.strategy.params), cfg).run()
    except KeyboardInterrupt:
        logging.info("停止しました(保有ポジションは MT5 上に残り、SL/TP は有効です)")
    finally:
        broker.shutdown()


def main(argv=None):
    p = argparse.ArgumentParser(prog="fxbot", description="FX 自動売買ボット(MT5)")
    p.add_argument("-c", "--config", default="config.yaml" if Path("config.yaml").exists() else None,
                   help="設定ファイル(省略時は ./config.yaml、無ければ既定値)")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backtest", help="過去データで戦略を検証")
    src = b.add_mutually_exclusive_group()
    src.add_argument("--csv", help="価格データ CSV")
    src.add_argument("--mt5", type=int, metavar="BARS", help="MT5 から直近 BARS 本を取得して検証")
    src.add_argument("--synthetic", type=int, default=5000, metavar="BARS", help="ランダムデータで動作確認")
    b.add_argument("--strategy", help=f"戦略名を上書き({', '.join(STRATEGIES)}, all)")
    b.add_argument("--trades-out", help="取引履歴の保存先 CSV")

    f = sub.add_parser("fetch", help="MT5 から足データを CSV に保存")
    f.add_argument("--bars", type=int, default=10000)
    f.add_argument("--out", default="data.csv")

    lv = sub.add_parser("live", help="MT5 デモ口座で自動売買を開始")
    lv.add_argument("--dry-run", action="store_true", help="発注せずログだけ出す")

    sub.add_parser("strategies", help="使える戦略の一覧")

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(args.config)

    if args.cmd == "strategies":
        for name, cls in STRATEGIES.items():
            print(f"{name:<14} {(cls.__doc__ or '').strip().splitlines()[0]}")
    elif args.cmd == "backtest":
        cmd_backtest(args, cfg)
    elif args.cmd == "fetch":
        cmd_fetch(args, cfg)
    elif args.cmd == "live":
        cmd_live(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
