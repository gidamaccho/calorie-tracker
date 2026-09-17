from datetime import datetime, timedelta, timezone

import pytest

from fxbot.models import EURUSD, Position, Side, USDJPY
from fxbot.risk import RiskConfig, RiskManager

MON = datetime(2024, 3, 4, 9, 0, tzinfo=timezone.utc)   # 月曜
SAT = datetime(2024, 3, 9, 9, 0, tzinfo=timezone.utc)   # 土曜


def mgr(equity=1_000_000.0, **kwargs):
    return RiskManager(RiskConfig(**kwargs), equity)


def entry(risk, **kwargs):
    params = dict(
        instrument=USDJPY, side=Side.BUY, entry_price=150.0, stop_price=149.50,
        equity=1_000_000.0, open_positions=[], now=MON,
    )
    params.update(kwargs)
    return risk.evaluate_entry(**params)


# --- ポジションサイズ ---------------------------------------------------

def test_position_size_risks_exactly_the_configured_fraction():
    """50pips の損切りで口座の1%を失う数量になること。"""
    risk = mgr(risk_per_trade=0.01)
    decision = entry(risk)
    assert decision.allowed
    loss_if_stopped = decision.units * 0.50  # 値幅(円) × 数量 = 円建て損失
    assert loss_if_stopped == pytest.approx(10_000, rel=0.05)


def test_wider_stop_gives_smaller_position():
    # レバレッジ上限が先に効かないよう緩めて、損切り幅だけの影響を見る
    risk = mgr(max_leverage=25.0)
    narrow = entry(risk, stop_price=149.80).units   # 20pips
    wide = entry(risk, stop_price=149.00).units     # 100pips
    assert narrow > wide
    # 損失額はどちらもほぼ同じ (これがリスク一定サイジングの要点)
    assert narrow * 0.20 == pytest.approx(wide * 1.00, rel=0.05)


def test_leverage_cap_binds_before_risk_sizing_on_narrow_stops():
    """損切りが狭いとリスク基準の数量が膨らみ、先にレバレッジ上限に当たる。

    既定 (リスク1%・上限5倍・資金100万) で20pips損切りだと、
    リスク基準では5万通貨 (=750万円相当, 7.5倍) になるため上限で削られる。
    """
    risk = mgr(max_leverage=5.0)
    decision = entry(risk, stop_price=149.80)
    assert decision.allowed
    assert decision.units * 150.0 <= 5.0 * 1_000_000 * 1.001
    # 結果として、想定損失は設定した1%より小さくなる
    assert decision.units * 0.20 < 10_000


def test_position_size_scales_with_equity():
    risk = mgr()
    small = entry(risk, equity=500_000).units
    large = entry(risk, equity=2_000_000).units
    assert large == pytest.approx(small * 4, rel=0.05)


def test_non_jpy_pair_uses_jpy_conversion_rate():
    risk = mgr()
    decision = risk.evaluate_entry(
        instrument=EURUSD, side=Side.BUY, entry_price=1.0800, stop_price=1.0750,
        equity=1_000_000.0, open_positions=[], now=MON, jpy_rate=150.0,
    )
    assert decision.allowed
    # 50pips = 0.005 USD/単位、USD/JPY=150 → 1単位あたり0.75円の損失
    assert decision.units * 0.005 * 150 == pytest.approx(10_000, rel=0.05)


def test_tiny_account_is_rejected_rather_than_undersized():
    """最小取引単位に満たない数量になるなら、丸めて発注せず拒否する。"""
    risk = mgr(equity=1_000)
    decision = entry(risk, equity=1_000)
    assert not decision.allowed
    assert "最小取引単位" in decision.reason


# --- 損切りの妥当性 -----------------------------------------------------

def test_stop_on_wrong_side_is_rejected():
    risk = mgr()
    assert not entry(risk, side=Side.BUY, stop_price=150.5).allowed
    assert not entry(risk, side=Side.SELL, stop_price=149.5).allowed


def test_stop_too_narrow_or_too_wide_is_rejected():
    risk = mgr(min_stop_pips=5, max_stop_pips=100)
    assert not entry(risk, stop_price=149.98).allowed  # 2pips
    assert not entry(risk, stop_price=148.00).allowed  # 200pips
    assert entry(risk, stop_price=149.50).allowed      # 50pips


def test_missing_stop_falls_back_to_default_pips():
    risk = mgr(default_stop_pips=20, max_leverage=25.0)
    decision = entry(risk, stop_price=None)
    assert decision.allowed
    assert decision.units * 0.20 == pytest.approx(10_000, rel=0.05)


# --- 建玉数・レバレッジ -------------------------------------------------

def test_max_positions_blocks_additional_entries():
    risk = mgr(max_positions=1)
    existing = Position(USDJPY, Side.BUY, 10_000, 150.0, MON)
    decision = entry(risk, open_positions=[existing])
    assert not decision.allowed
    assert "上限" in decision.reason


def test_leverage_cap_shrinks_position_instead_of_rejecting():
    """レバレッジ上限に当たったら、拒否ではなく収まるサイズまで減らす。"""
    risk = mgr(risk_per_trade=0.50, max_leverage=2.0)  # 極端なリスク設定
    decision = entry(risk, stop_price=149.99 - 0.0)     # あえて狭い損切り
    decision = entry(risk, stop_price=149.90)           # 10pips
    assert decision.allowed
    notional = decision.units * 150.0
    assert notional <= 2.0 * 1_000_000 * 1.001


def test_existing_exposure_counts_towards_leverage_cap():
    risk = mgr(risk_per_trade=0.5, max_leverage=2.0, max_positions=2)
    existing = Position(USDJPY, Side.BUY, 13_000, 150.0, MON)  # 約195万円相当
    decision = entry(risk, stop_price=149.90, open_positions=[existing])
    if decision.allowed:
        total = decision.units * 150.0 + existing.notional(150.0)
        assert total <= 2.0 * 1_000_000 * 1.001
    else:
        assert "レバレッジ" in decision.reason


# --- 取引停止条件 -------------------------------------------------------

def test_consecutive_losses_halt_trading():
    risk = mgr(max_consecutive_losses=3)
    for _ in range(3):
        risk.on_trade_closed(-5_000)
    assert risk.state.halted
    assert not entry(risk).allowed


def test_a_win_resets_the_losing_streak():
    risk = mgr(max_consecutive_losses=3)
    risk.on_trade_closed(-5_000)
    risk.on_trade_closed(-5_000)
    risk.on_trade_closed(+1_000)
    risk.on_trade_closed(-5_000)
    assert not risk.state.halted
    assert risk.state.consecutive_losses == 1


def test_daily_loss_limit_halts_and_resets_next_day():
    risk = mgr(daily_loss_limit=0.03)
    risk.on_new_bar(MON, 1_000_000)
    risk.on_new_bar(MON + timedelta(hours=1), 960_000)  # -4%
    assert risk.state.halted
    assert "日次" in risk.state.halt_reason

    # 翌日は再開する
    risk.on_new_bar(MON + timedelta(days=1), 960_000)
    assert not risk.state.halted


def test_max_drawdown_halt_persists_across_days():
    """最大DDによる停止は日付が変わっても解除されない (手動確認が必要)。"""
    risk = mgr(max_drawdown=0.10, daily_loss_limit=1.0)
    risk.on_new_bar(MON, 1_000_000)
    risk.on_new_bar(MON + timedelta(hours=1), 850_000)
    assert risk.state.halted
    risk.on_new_bar(MON + timedelta(days=3), 850_000)
    assert risk.state.halted

    risk.resume()
    assert not risk.state.halted


def test_drawdown_measured_from_peak_not_from_start():
    risk = mgr(max_drawdown=0.10, daily_loss_limit=1.0)
    risk.on_new_bar(MON, 1_000_000)
    risk.on_new_bar(MON + timedelta(hours=1), 2_000_000)  # ピーク更新
    risk.on_new_bar(MON + timedelta(hours=2), 1_700_000)  # ピークから-15%
    assert risk.state.halted


# --- フィルタ -----------------------------------------------------------

def test_weekend_is_blocked_by_default():
    risk = mgr()
    assert not entry(risk, now=SAT).allowed
    assert entry(mgr(trade_on_weekend=True), now=SAT).allowed


def test_trading_hours_window():
    risk = mgr(trading_hours=(7, 20))
    assert entry(risk, now=MON.replace(hour=9)).allowed
    assert not entry(risk, now=MON.replace(hour=3)).allowed


def test_overnight_trading_hours_wrap_midnight():
    risk = mgr(trading_hours=(22, 6))
    assert entry(risk, now=MON.replace(hour=23)).allowed
    assert entry(risk, now=MON.replace(hour=2)).allowed
    assert not entry(risk, now=MON.replace(hour=12)).allowed


def test_wide_spread_blocks_entry():
    risk = mgr(max_spread_pips=3.0)
    assert not entry(risk, spread_pips=8.0).allowed
    assert entry(risk, spread_pips=1.0).allowed


# --- トレーリングストップ ----------------------------------------------

def test_trailing_stop_only_moves_in_profit_direction():
    risk = mgr(trailing_stop_pips=20, trailing_trigger_pips=30)
    position = Position(USDJPY, Side.BUY, 10_000, 150.0, MON, stop_price=149.50)

    assert not risk.update_trailing_stop(position, 150.10)  # 利益が発動条件未満
    assert position.stop_price == pytest.approx(149.50)

    assert risk.update_trailing_stop(position, 150.60)      # +60pips
    assert position.stop_price == pytest.approx(150.40)

    # 価格が戻ってもストップは下がらない
    assert not risk.update_trailing_stop(position, 150.20)
    assert position.stop_price == pytest.approx(150.40)


def test_trailing_stop_for_short_position():
    risk = mgr(trailing_stop_pips=20, trailing_trigger_pips=30)
    position = Position(USDJPY, Side.SELL, 10_000, 150.0, MON, stop_price=150.50)
    assert risk.update_trailing_stop(position, 149.40)
    assert position.stop_price == pytest.approx(149.60)


def test_trailing_disabled_by_default():
    risk = mgr()
    position = Position(USDJPY, Side.BUY, 10_000, 150.0, MON, stop_price=149.5)
    assert not risk.update_trailing_stop(position, 155.0)
    assert position.stop_price == pytest.approx(149.5)
