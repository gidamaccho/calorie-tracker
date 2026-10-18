from datetime import date

from fxbot.risk import DailyLossGuard, calc_lots, pip_size


def test_calc_lots_respects_risk():
    # 100 万円、1% = 1 万円リスク、損切り 0.5 円、1 ロット = 10 万通貨
    lots = calc_lots(1_000_000, 1.0, 0.5, 100_000, 0.01, 0.01, 50)
    assert lots == 0.2
    assert lots * 0.5 * 100_000 <= 10_000


def test_calc_lots_rounds_down_and_min_lot():
    assert calc_lots(1_000_000, 1.0, 0.3, 100_000, 0.01, 0.01, 50) == 0.33
    assert calc_lots(10_000, 1.0, 1.0, 100_000, 0.01, 0.01, 50) == 0.0
    assert calc_lots(1e12, 1.0, 0.1, 100_000, 0.01, 0.01, 50) == 50


def test_pip_size():
    assert pip_size("USDJPY") == 0.01
    assert pip_size("EURUSD") == 0.0001


def test_daily_loss_guard():
    g = DailyLossGuard(3.0)
    d1, d2 = date(2024, 1, 1), date(2024, 1, 2)
    assert g.can_open(d1, 100_000)
    assert g.can_open(d1, 97_500)
    assert not g.can_open(d1, 96_999)
    assert g.can_open(d2, 96_999)  # 翌日はリセット
