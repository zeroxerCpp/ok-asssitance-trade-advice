"""
tests/test_signals_unit.py — Unit tests for SignalEngine signal methods + smoke test.

A synthetic MarketData is constructed for each test; no OKX CLI I/O is needed.
"""
import unittest

from engine.models import Candle, MarketData, SignalResult
from engine.signals import SignalEngine


# ─────────────────────────────────────────────────────────────────────────────
# Factory helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_candles(n, start_close=100.0, step=0.5, vol=1000.0):
    """Return *n* confirmed Candle objects with a linearly changing close."""
    candles = []
    for i in range(n):
        c = start_close + i * step
        candles.append(Candle(
            ts=i,
            open=c,
            high=c + 1.0,
            low=c - 1.0,
            close=c,
            vol=vol,
            confirm="1",
        ))
    return candles


def make_market_data(
    *,
    step_4h=0.5,
    step_1h=0.5,
    vol_4h=1000.0,
    vol_1h=1000.0,
    funding_rate=0.0,
    open_interest=10_000.0,
    bids_top10=None,
    asks_top10=None,
    trades=None,
    last_price=200.0,
):
    """Build a minimal MarketData with 200 confirmed 4H and 1H candles."""
    c4 = _make_candles(200, start_close=100.0, step=step_4h, vol=vol_4h)
    c1 = _make_candles(200, start_close=100.0, step=step_1h, vol=vol_1h)

    if bids_top10 is None:
        bids_top10 = [(last_price, 10.0)] * 10
    if asks_top10 is None:
        asks_top10 = [(last_price, 10.0)] * 10
    if trades is None:
        trades = [{"side": "buy"}] * 25 + [{"side": "sell"}] * 25

    return MarketData(
        inst_id="BTC-USDT-SWAP",
        candles_1d=[],
        candles_4h=c4,
        candles_1h=c1,
        last_price=last_price,
        funding_rate=funding_rate,
        open_interest=open_interest,
        oi_history=[open_interest] * 10,
        liquidations=[],
        bids_top10=bids_top10,
        asks_top10=asks_top10,
        trades=trades,
        timestamp="2026-01-01T00:00:00Z",
        candles_15m=[],
    )


# ─────────────────────────────────────────────────────────────────────────────
# _sig_ema
# ─────────────────────────────────────────────────────────────────────────────

class TestSigEma(unittest.TestCase):

    def test_bullish_rising_series(self):
        # Linearly rising series → EMA9 > EMA21 for many candles → sign == +1
        data = make_market_data(step_4h=1.0)
        eng  = SignalEngine(data, account_size=10_000)
        sig  = eng._sig_ema()
        self.assertEqual(sig.sign, +1)

    def test_result_is_signal_result(self):
        data = make_market_data(step_4h=1.0)
        eng  = SignalEngine(data, account_size=10_000)
        sig  = eng._sig_ema()
        self.assertIsInstance(sig, SignalResult)
        self.assertAlmostEqual(sig.vote, sig.sign * sig.confidence)

    def test_bearish_falling_series(self):
        # Falling series → EMA9 < EMA21 → sign == -1
        data = make_market_data(step_4h=-0.5, last_price=1.0)
        # Adjust start_close to keep prices positive throughout 200 bars
        c4 = _make_candles(200, start_close=200.0, step=-0.5, vol=1000.0)
        c1 = _make_candles(200, start_close=200.0, step=-0.5, vol=1000.0)
        data.candles_4h = c4
        data.candles_1h = c1
        data.last_price = c4[-1].close

        eng = SignalEngine(data, account_size=10_000)
        sig = eng._sig_ema()
        self.assertEqual(sig.sign, -1)


# ─────────────────────────────────────────────────────────────────────────────
# _sig_volume_breakout
# ─────────────────────────────────────────────────────────────────────────────

class TestSigVolumeBreakout(unittest.TestCase):

    def test_volume_spike_bullish(self):
        # Last 1H candle has vol = 3 × MA20 and close > open (bullish)
        vol_normal = 1000.0
        vol_spike  = vol_normal * 3.0
        c1 = _make_candles(200, start_close=100.0, step=0.5, vol=vol_normal)
        # Make the last candle a spike up candle
        last = c1[-1]
        c1[-1] = Candle(
            ts=last.ts, open=last.open - 1.0,
            high=last.close + 1.0, low=last.open - 2.0,
            close=last.close, vol=vol_spike, confirm="1",
        )

        data = make_market_data()
        data.candles_1h = c1
        eng = SignalEngine(data, account_size=10_000)
        sig = eng._sig_volume_breakout()
        self.assertEqual(sig.sign, +1)
        self.assertAlmostEqual(sig.confidence, 1.0)

    def test_normal_volume_neutral(self):
        data = make_market_data(vol_1h=1000.0)
        eng  = SignalEngine(data, account_size=10_000)
        sig  = eng._sig_volume_breakout()
        self.assertEqual(sig.sign, 0)


# ─────────────────────────────────────────────────────────────────────────────
# _sig_funding
# ─────────────────────────────────────────────────────────────────────────────

class TestSigFunding(unittest.TestCase):

    def test_high_positive_funding_bearish(self):
        # 0.0008 → fr_pct = 0.08 > 0.05 → sign == -1
        data = make_market_data(funding_rate=0.0008)
        eng  = SignalEngine(data, account_size=10_000, is_swap=True)
        sig  = eng._sig_funding()
        self.assertEqual(sig.sign, -1)

    def test_negative_funding_bullish(self):
        # -0.0002 → fr_pct = -0.02 < -0.01 → sign == +1
        data = make_market_data(funding_rate=-0.0002)
        eng  = SignalEngine(data, account_size=10_000, is_swap=True)
        sig  = eng._sig_funding()
        self.assertEqual(sig.sign, +1)

    def test_neutral_funding(self):
        # 0.0001 → fr_pct = 0.01 (between -0.01 and 0.05) → sign == 0
        data = make_market_data(funding_rate=0.0001)
        eng  = SignalEngine(data, account_size=10_000, is_swap=True)
        sig  = eng._sig_funding()
        self.assertEqual(sig.sign, 0)

    def test_spot_skipped(self):
        data = make_market_data(funding_rate=0.001)
        eng  = SignalEngine(data, account_size=10_000, is_swap=False)
        sig  = eng._sig_funding()
        self.assertEqual(sig.sign, 0)


# ─────────────────────────────────────────────────────────────────────────────
# _sig_orderbook
# ─────────────────────────────────────────────────────────────────────────────

class TestSigOrderbook(unittest.TestCase):

    def test_bid_dominant_bullish(self):
        # bids value = 13,000; asks value = 10,000 → ratio 1.3 > 1.2 → +1
        bids = [(1000.0, 13.0)]
        asks = [(1000.0, 10.0)]
        data = make_market_data(bids_top10=bids, asks_top10=asks)
        eng  = SignalEngine(data, account_size=10_000)
        sig  = eng._sig_orderbook()
        self.assertEqual(sig.sign, +1)

    def test_ask_dominant_bearish(self):
        # asks value = 13,000; bids value = 10,000 → ratio 10/13 < 1/1.2 → -1
        bids = [(1000.0, 10.0)]
        asks = [(1000.0, 13.0)]
        data = make_market_data(bids_top10=bids, asks_top10=asks)
        eng  = SignalEngine(data, account_size=10_000)
        sig  = eng._sig_orderbook()
        self.assertEqual(sig.sign, -1)


# ─────────────────────────────────────────────────────────────────────────────
# _sig_trade_flow
# ─────────────────────────────────────────────────────────────────────────────

class TestSigTradeFlow(unittest.TestCase):

    def test_buy_dominant(self):
        trades = [{"side": "buy"}] * 40 + [{"side": "sell"}] * 10
        data   = make_market_data(trades=trades)
        eng    = SignalEngine(data, account_size=10_000)
        sig    = eng._sig_trade_flow()
        self.assertEqual(sig.sign, +1)

    def test_sell_dominant(self):
        trades = [{"side": "buy"}] * 10 + [{"side": "sell"}] * 40
        data   = make_market_data(trades=trades)
        eng    = SignalEngine(data, account_size=10_000)
        sig    = eng._sig_trade_flow()
        self.assertEqual(sig.sign, -1)

    def test_balanced_flow_neutral(self):
        trades = [{"side": "buy"}] * 25 + [{"side": "sell"}] * 25
        data   = make_market_data(trades=trades)
        eng    = SignalEngine(data, account_size=10_000)
        sig    = eng._sig_trade_flow()
        self.assertEqual(sig.sign, 0)


# ─────────────────────────────────────────────────────────────────────────────
# Full run smoke test
# ─────────────────────────────────────────────────────────────────────────────

class TestSignalEngineSmoke(unittest.TestCase):

    def test_run_completes_without_exception(self):
        data   = make_market_data()
        report = SignalEngine(data, account_size=10_000).run()
        self.assertIsNotNone(report)

    def test_report_direction_valid(self):
        data   = make_market_data()
        report = SignalEngine(data, account_size=10_000).run()
        self.assertIn(report.direction, {"LONG", "SHORT", "NEUTRAL"})

    def test_report_total_score_in_range(self):
        data   = make_market_data()
        report = SignalEngine(data, account_size=10_000).run()
        self.assertGreaterEqual(report.total_score, -10.0)
        self.assertLessEqual(report.total_score, 10.0)

    def test_report_market_state_non_empty(self):
        data   = make_market_data()
        report = SignalEngine(data, account_size=10_000).run()
        self.assertTrue(len(report.market_state) > 0)

    def test_report_as_dict_has_required_keys(self):
        data   = make_market_data()
        report = SignalEngine(data, account_size=10_000).run()
        d = report.as_dict()
        for key in ("inst_id", "direction", "total_score", "market_state"):
            self.assertIn(key, d)


if __name__ == "__main__":
    unittest.main()
