# fxbot — FX 自動売買システム(MetaTrader 5 用)

MT5 のデモ口座で動く FX 自動売買ボットと、戦略を検証するバックテスターです。

> ⚠️ **注意**: このコードは利益を保証しません。同梱の戦略は「動く仕組みの見本」で、
> そのまま使って勝てるようには調整されていません。必ずバックテストとデモ口座で十分に検証してください。
> 既定ではリアル口座への接続を拒否するようにしてあります。

## できること

| 機能 | コマンド |
|---|---|
| バックテスト(CSV / MT5 の過去データ / ランダムデータ) | `python -m fxbot backtest` |
| MT5 から足データを CSV に保存 | `python -m fxbot fetch` |
| デモ口座で自動売買 | `python -m fxbot live` |
| 戦略の一覧 | `python -m fxbot strategies` |

**戦略(設定で切り替え)**
- `ma_cross` — 移動平均クロス(トレンドフォロー)。短期線が長期線を上抜けで買い、下抜けで売り
- `rsi_reversal` — RSI 逆張り。売られすぎ(30 未満)から戻したら買い、買われすぎ(70 超)から戻したら売り

**資金管理(全戦略共通)**
- 損切り = ATR × 2、利確 = ATR × 3(倍率は設定可)
- ロット数は「損切りに掛かったら資金の 1% を失う」量を自動計算
- 1 日に資金が 3% 減ったら、その日の新規エントリーを停止
- スプレッドが広すぎるときはエントリーを見送り
- 反対シグナルで決済してドテン

## セットアップ

MT5 の Python 連携は **Windows 専用** です(バックテストは Mac/Linux でも動きます)。

1. MT5 をインストールし、業者のデモ口座でログインする
2. MT5 の「ツール → オプション → エキスパートアドバイザ」で **「アルゴリズム取引を許可」** にチェック
3. Python 3.10 以上で:
   ```powershell
   cd fx-trader
   pip install -r requirements.txt
   copy config.example.yaml config.yaml
   ```
4. 業者によって銘柄名が `USDJPY` ではなく `USDJPY.a` などの場合は `config.yaml` の `symbol` を合わせる

MT5 がすでにログイン済みなら追加設定は不要です。別の口座を指定する場合は環境変数で渡します(パスワードを設定ファイルに書かないため):
```powershell
$env:MT5_LOGIN="12345678"; $env:MT5_PASSWORD="xxxx"; $env:MT5_SERVER="XXXX-Demo"
```

## 使い方

### 1. バックテスト
```bash
python -m fxbot backtest                      # ランダムデータで動作確認
python -m fxbot backtest --mt5 20000          # MT5 から直近 2 万本を取得して検証
python -m fxbot backtest --csv data.csv --strategy all --trades-out trades.csv
```
CSV は `time,open,high,low,close` 形式か、MT5 の「チャート → エクスポート」で保存したものがそのまま使えます。

約定ルールは保守的にしてあります: シグナルは足の確定で判定し**次の足の始値**で約定、スプレッド込み、
同じ足で損切りと利確の両方に届いたら**損切り扱い**。

### 2. デモ口座で自動売買
```bash
python -m fxbot live --dry-run   # まずは発注せずにログだけ確認
python -m fxbot live             # デモ口座で発注開始(Ctrl+C で停止)
```
- 足が確定するたびにシグナルを判定します(起動直後の足では入りません)
- 注文には `magic` 番号が付き、このボットのポジションだけを管理します
- 停止してもポジションは MT5 上に残り、損切り・利確は MT5 側で有効なままです
- ログは `logs/fxbot.log` に保存されます

### リアル口座について
既定では、接続先がリアル口座だと起動を拒否します。十分に検証したうえで使う場合のみ、
`config.yaml` の `live.allow_live_account: true` **と** 環境変数 `FXBOT_ALLOW_LIVE=yes` の両方を設定してください。

## 戦略を追加する

`fxbot/strategies/` に `Strategy` を継承したクラスを作り、`signals()` で各足のシグナル(1=買い, -1=売り, 0=なし)を返します。
`fxbot/strategies/__init__.py` の `STRATEGIES` に登録すれば、設定の `strategy.name` で選べるようになります。

```python
class MyStrategy(Strategy):
    name = "my_strategy"

    @property
    def min_bars(self):
        return 50

    def signals(self, df):
        ...  # i 番目の値は i 番目までの足だけで計算すること(未来のデータを使わない)
```

## 構成

```
fxbot/
  strategies/   戦略(ma_cross, rsi_reversal)
  indicators.py SMA / EMA / RSI / ATR
  risk.py       ロット計算・日次損失ストップ
  backtest.py   バックテスター
  broker.py     MT5 接続・発注
  live.py       自動売買ループ
  config.py     設定ファイル読み込み
tests/          pytest(MT5 なしで実行可能)
```

テスト: `python -m pytest`

## 補足
- バックテストの損益計算は「決済通貨 → 口座通貨」の換算を固定レート(`quote_to_account_rate`)で行います。
  USDJPY × 円口座なら 1.0 のままで正確です。ライブでは MT5 の銘柄情報から正しく換算します。
- 過去の成績は将来の成績を保証しません。過剰なパラメータ調整(過剰最適化)にも注意してください。
