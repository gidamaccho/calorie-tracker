import pytest

from fxbot.models import Position, Side, SignalType, USDJPY
from fxbot.strategies import REGISTRY, build_strategy
from fxbot.strategies.breakout import BreakoutStrategy
from fxbot.strategies.rsi_reversion import RsiReversionStrategy
from fxbot.strategies.sma_cross import SmaCrossStrategy
from tests.conftest import T0, make_candles


def feed_all(strategy, candles, position=None):
    """全足を流し込み、各足のシグナルを返す。"""
    signals = []
    for candle in candles:
        strategy.feed(candle)
        signals.append(strategy.on_candle(position))
    return signals


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_strategy_stays_silent_before_warmup(name):
    """warmup 本に満たない間はシグナルを出さないこと。

    指標が None の期間に発注すると、根拠のないトレードになる。
    """
    strategy = build_strategy(name, USDJPY)
    candles = make_candles([150.0 + i * 0.01 for i in range(strategy.warmup - 1)])
    for signal in feed_all(strategy, candles):
        assert signal.type is SignalType.NONE


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_entry_signals_always_carry_a_stop(name):
    """エントリーには必ず損切り価格が付くこと。

    損切りの無いエントリーは、リスク管理の既定値頼みになる。
    """
    strategy = build_strategy(name, USDJPY)
    prices = [150.0 + 2.0 * (i / 300) for i in range(400)]  # 上昇トレンド
    for signal in feed_all(strategy, make_candles(prices)):
        if signal.is_entry:
            assert signal.stop_price is not None
            if signal.type is SignalType.ENTRY_LONG:
                assert signal.stop_price < strategy.candles[-1].close
            else:
                assert signal.stop_price > strategy.candles[-1].close


def test_sma_cross_rejects_fast_slower_than_slow():
    with pytest.raises(ValueError):
        SmaCrossStrategy(USDJPY, fast=50, slow=20)


def test_sma_cross_goes_long_on_golden_cross_in_uptrend():
    strategy = SmaCrossStrategy(USDJPY, fast=3, slow=8, use_trend_filter=False, atr_period=5)
    # 下げてから明確に上げ、短期MAが長期MAを上抜ける形を作る
    prices = [150.0 - i * 0.05 for i in range(20)] + [149.0 + i * 0.15 for i in range(25)]
    signals = feed_all(strategy, make_candles(prices))
    assert any(s.type is SignalType.ENTRY_LONG for s in signals)


def test_sma_cross_trend_filter_blocks_counter_trend_entries():
    """長期トレンドに逆らうエントリーがフィルタで減ること。"""
    prices = [150.0 - i * 0.02 for i in range(120)]  # 一貫した下降
    prices += [147.6 + (i % 6) * 0.05 for i in range(40)]  # 小さな戻り

    unfiltered = SmaCrossStrategy(USDJPY, fast=3, slow=8, use_trend_filter=False, atr_period=5)
    filtered = SmaCrossStrategy(
        USDJPY, fast=3, slow=8, use_trend_filter=True, trend_period=50, atr_period=5
    )
    longs_unfiltered = sum(
        1 for s in feed_all(unfiltered, make_candles(prices)) if s.type is SignalType.ENTRY_LONG
    )
    longs_filtered = sum(
        1 for s in feed_all(filtered, make_candles(prices)) if s.type is SignalType.ENTRY_LONG
    )
    assert longs_filtered <= longs_unfiltered


def test_sma_cross_exits_long_on_dead_cross():
    strategy = SmaCrossStrategy(USDJPY, fast=3, slow=8, use_trend_filter=False, atr_period=5)
    prices = [150.0 + i * 0.1 for i in range(20)] + [152.0 - i * 0.2 for i in range(20)]
    position = Position(USDJPY, Side.BUY, 10_000, 150.0, T0)
    signals = feed_all(strategy, make_candles(prices), position=position)
    assert any(s.type is SignalType.EXIT for s in signals)


def test_rsi_validates_thresholds():
    with pytest.raises(ValueError):
        RsiReversionStrategy(USDJPY, oversold=70, overbought=30)


def test_rsi_buys_on_recovery_from_oversold_not_on_the_way_down():
    """下落の途中ではなく、反転を確認してから買うこと。"""
    strategy = RsiReversionStrategy(USDJPY, rsi_period=5, atr_period=5, oversold=30)
    falling = [150.0 - i * 0.2 for i in range(20)]
    signals_down = feed_all(strategy, make_candles(falling))
    assert not any(s.is_entry for s in signals_down)  # 落下中は入らない

    rising = [146.0 + i * 0.25 for i in range(10)]
    signals_up = feed_all(strategy, make_candles(rising, start=strategy.candles[-1].time))
    assert any(s.type is SignalType.ENTRY_LONG for s in signals_up)


def test_rsi_exits_when_back_to_neutral():
    strategy = RsiReversionStrategy(USDJPY, rsi_period=5, atr_period=5, exit_level=50)
    prices = [150.0 - i * 0.2 for i in range(15)] + [147.0 + i * 0.3 for i in range(10)]
    position = Position(USDJPY, Side.BUY, 10_000, 147.0, T0)
    signals = feed_all(strategy, make_candles(prices), position=position)
    assert any(s.type is SignalType.EXIT for s in signals)


def test_breakout_enters_on_new_high():
    strategy = BreakoutStrategy(USDJPY, entry_period=10, exit_period=5, atr_period=5)
    prices = [150.0 + (i % 3) * 0.05 for i in range(30)]  # 狭いレンジ
    prices += [151.5, 152.0]                              # 明確な上抜け
    signals = feed_all(strategy, make_candles(prices))
    assert any(s.type is SignalType.ENTRY_LONG for s in signals)


def test_breakout_does_not_use_current_bar_in_its_own_channel():
    """自分自身の高値を含めたチャネルと比較すると、絶対に上抜けできない。

    このテストは、チャネル計算から現在足を除いていることを担保する。
    """
    strategy = BreakoutStrategy(USDJPY, entry_period=5, exit_period=3, atr_period=3)
    prices = [150.0] * 12 + [155.0]
    signals = feed_all(strategy, make_candles(prices))
    assert signals[-1].type is SignalType.ENTRY_LONG


def test_breakout_exits_on_opposite_channel():
    strategy = BreakoutStrategy(USDJPY, entry_period=10, exit_period=3, atr_period=5)
    prices = [150.0 + i * 0.1 for i in range(20)] + [151.0, 150.0, 149.0, 148.0]
    position = Position(USDJPY, Side.BUY, 10_000, 151.0, T0)
    signals = feed_all(strategy, make_candles(prices), position=position)
    assert any(s.type is SignalType.EXIT for s in signals)


def test_registry_rejects_unknown_strategy():
    with pytest.raises(KeyError):
        build_strategy("存在しない戦略", USDJPY)


def test_history_is_trimmed_to_bound_memory():
    """長期稼働でメモリが際限なく増えないこと。"""
    strategy = SmaCrossStrategy(USDJPY, fast=3, slow=8, use_trend_filter=False)
    for candle in make_candles([150.0 + (i % 10) * 0.01 for i in range(5000)]):
        strategy.feed(candle)
    assert len(strategy.candles) < 2000
