from datetime import datetime, timedelta, timezone

import pytest

from fxbot.brokers.base import BrokerError
from fxbot.brokers.paper import PaperBroker
from fxbot.engine import EngineConfig, TradingEngine, _CandleBuilder
from fxbot.models import Candle, Signal, Tick, USDJPY
from fxbot.strategies.base import Strategy

T = datetime(2024, 3, 4, 9, 5, tzinfo=timezone.utc)


class Silent(Strategy):
    name = "silent"

    @property
    def warmup(self):
        return 2

    def on_candle(self, position):
        return Signal.none()


# --- 足の組み立て -------------------------------------------------------

def test_builder_returns_nothing_until_the_bar_completes():
    b = _CandleBuilder(60)
    assert b.update(T, 150.0) is None
    assert b.update(T + timedelta(minutes=30), 150.5) is None


def test_builder_emits_previous_bar_when_time_moves_on():
    b = _CandleBuilder(60)
    b.update(T, 150.0)
    b.update(T + timedelta(minutes=10), 150.5)
    b.update(T + timedelta(minutes=20), 149.8)
    candle = b.update(T + timedelta(minutes=60), 150.3)

    assert candle is not None
    assert candle.time == T.replace(minute=0)   # 9:00 の足
    assert candle.open == pytest.approx(150.0)
    assert candle.high == pytest.approx(150.5)
    assert candle.low == pytest.approx(149.8)
    assert candle.close == pytest.approx(149.8)  # 9時台の最後の値


def test_builder_buckets_align_to_the_clock():
    b = _CandleBuilder(15)
    assert b._bucket(T.replace(minute=7)) == T.replace(minute=0)
    assert b._bucket(T.replace(minute=17)) == T.replace(minute=15)
    assert b._bucket(T.replace(minute=59)) == T.replace(minute=45)


def test_builder_rejects_invalid_bar_length():
    with pytest.raises(ValueError):
        _CandleBuilder(0)


# --- エンジン -----------------------------------------------------------

class ScriptedSource:
    """決められた価格列を順に返す価格供給源。尽きたらエラーにする。

    PaperBroker の get_tick を差し替えるのではなく price_source として渡すことで、
    本番と同じ経路 (損切り判定を含む) を通す。
    """

    def __init__(self, prices, times):
        self._script = list(zip(times, prices))
        self._index = 0
        self.tick_calls = 0

    def connect(self):
        self._index = 0

    def disconnect(self):
        pass

    def get_tick(self, instrument):
        self.tick_calls += 1
        if self._index >= len(self._script):
            raise BrokerError("価格列が尽きた")
        when, price = self._script[self._index]
        self._index += 1
        half = instrument.pips_to_price(0.4) / 2
        return Tick(time=when, bid=price - half, ask=price + half)


def make_broker(prices, times, **kwargs):
    source = ScriptedSource(prices, times)
    broker = PaperBroker(starting_balance=1_000_000.0, price_source=source, **kwargs)
    broker.scripted = source
    return broker


def make_engine(prices, times, strategy=None, risk_config=None, **engine_kwargs):
    broker = make_broker(prices, times)
    config = EngineConfig(bar_minutes=60, poll_seconds=0.0,
                          max_consecutive_errors=1, **engine_kwargs)
    return TradingEngine(
        broker=broker,
        strategy=strategy or Silent(USDJPY),
        instrument=USDJPY,
        risk_config=risk_config,
        engine_config=config,
    ), broker


def test_engine_stops_after_consecutive_broker_errors():
    """価格が取れなくなったら、無限に再試行せず止まること。"""
    times = [T + timedelta(minutes=60 * i) for i in range(3)]
    engine, broker = make_engine([150.0, 150.1, 150.2], times)
    engine.run()
    # 価格列 (3件) を消費したあとエラーで停止する
    assert broker.scripted.tick_calls == 4


def test_engine_feeds_only_completed_bars_to_the_strategy():
    class Counting(Silent):
        def __init__(self, instrument):
            super().__init__(instrument)
            self.calls = 0

        def on_candle(self, position):
            self.calls += 1
            return Signal.none()

    # 同じ1時間の中で3ティック、その後次の時間へ
    times = [T, T + timedelta(minutes=10), T + timedelta(minutes=20),
             T + timedelta(minutes=60)]
    strategy = Counting(USDJPY)
    engine, _ = make_engine([150.0, 150.1, 150.2, 150.3], times, strategy)
    engine.run()
    # 確定した足は1本だけなので、判断も1回だけ
    assert strategy.calls == 1


def test_warmup_candles_prime_the_strategy():
    strategy = Silent(USDJPY)
    warmup = [
        Candle(T - timedelta(hours=i), 150.0, 150.1, 149.9, 150.0)
        for i in range(10, 0, -1)
    ]
    engine, _ = make_engine([150.0], [T], strategy)
    engine2 = TradingEngine(
        broker=engine.broker,
        strategy=strategy,
        instrument=USDJPY,
        warmup_candles=warmup,
    )
    assert len(strategy.candles) == 10
    assert strategy.ready


def test_engine_closes_positions_on_stop_when_configured():
    from fxbot.models import Order, Side

    times = [T + timedelta(minutes=60 * i) for i in range(2)]
    engine, broker = make_engine([150.0, 150.1], times, close_positions_on_stop=True)
    broker.set_market(USDJPY, Candle(T, 150.0, 150.0, 150.0, 150.0))
    broker.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=140.0))
    assert broker.get_positions()

    engine.run()
    assert broker.get_positions() == []


def test_engine_leaves_positions_open_by_default():
    from fxbot.models import Order, Side

    times = [T + timedelta(minutes=60 * i) for i in range(2)]
    engine, broker = make_engine([150.0, 150.1], times)
    broker.set_market(USDJPY, Candle(T, 150.0, 150.0, 150.0, 150.0))
    broker.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.0))

    engine.run()
    assert len(broker.get_positions()) == 1


# --- 業者側決済の回収 ---------------------------------------------------

def test_engine_records_stop_outs_from_the_broker():
    """損切り・利確による決済が、リスク管理と記録に必ず届くこと。

    実運用では決済の大半がこの経路。ここが抜けると連敗カウントが効かず、
    取引記録にも残らない。
    """
    from fxbot.models import Order, Side

    times = [T + timedelta(minutes=60 * i) for i in range(4)]
    # 150.0 で買い、149.0 まで落として損切りを踏ませる
    engine, broker = make_engine([150.0, 149.5, 148.5, 148.0], times)
    broker.set_market(USDJPY, Candle(T, 150.0, 150.0, 150.0, 150.0))
    broker.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.0))

    engine.run()

    assert broker.get_positions() == []
    assert len(broker.trades) == 1
    assert broker.trades[0].exit_reason == "損切り"
    # リスク管理が損失を認識していること
    assert engine.risk.state.consecutive_losses == 1


def test_stop_out_counts_towards_the_halt_threshold():
    from fxbot.models import Order, Side

    from fxbot.risk import RiskConfig

    times = [T + timedelta(minutes=60 * i) for i in range(4)]
    # 上昇で売り建玉が、続く下落で買い建玉が、それぞれ損切りに掛かる
    prices = [150.0, 151.0, 148.0, 148.0]
    engine, broker = make_engine(
        prices, times,
        risk_config=RiskConfig(max_consecutive_losses=2, daily_loss_limit=1.0),
    )
    broker.set_market(USDJPY, Candle(T, 150.0, 150.0, 150.0, 150.0))
    broker.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.5))
    broker.place_order(Order(USDJPY, Side.SELL, 10_000, stop_price=150.5))

    engine.run()
    assert engine.risk.state.halted


def test_poll_closed_trades_drains_once():
    """同じ決済を二重に数えないこと。"""
    from fxbot.models import Order, Side

    broker = PaperBroker(starting_balance=1_000_000.0)
    broker.connect()
    broker.set_market(USDJPY, Candle(T, 150.0, 150.0, 150.0, 150.0))
    broker.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.0))
    broker.check_stops(USDJPY, 148.5, T + timedelta(hours=1))

    assert len(broker.poll_closed_trades()) == 1
    assert broker.poll_closed_trades() == []


def test_manual_close_is_not_double_counted():
    """close_position で決済したぶんは、回収経路に流れないこと。

    両方に載ると、1回の損失が2回分としてカウントされる。
    """
    from fxbot.models import Order, Side

    broker = PaperBroker(starting_balance=1_000_000.0)
    broker.connect()
    broker.set_market(USDJPY, Candle(T, 150.0, 150.0, 150.0, 150.0))
    position = broker.place_order(Order(USDJPY, Side.BUY, 10_000, stop_price=149.0))
    broker.close_position(position, "手動")
    assert broker.poll_closed_trades() == []
