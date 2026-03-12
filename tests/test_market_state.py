"""
tests/test_market_state.py — Unit tests for engine.market_state.detect_market_state.
"""
import unittest

from engine.models import Candle
from engine.market_state import detect_market_state


def make_candles(n, high=100.0, low=99.0, close=99.5, vol=1000.0):
    """Return *n* confirmed Candle objects with the given OHLCV values."""
    return [
        Candle(ts=i, open=close, high=high, low=low, close=close, vol=vol, confirm="1")
        for i in range(n)
    ]


class TestDetectMarketState(unittest.TestCase):

    def test_trending_state_with_uptrend(self):
        # Build 200 4H candles with a clear uptrend (close 100 → 200)
        n = 200
        candles_4h = [
            Candle(
                ts=i,
                open=100.0 + i * 0.5,
                high=100.0 + i * 0.5 + 1.0,
                low=100.0  + i * 0.5 - 1.0,
                close=100.0 + i * 0.5,
                vol=1000.0,
                confirm="1",
            )
            for i in range(n)
        ]
        candles_1h = make_candles(200, high=100.0, low=99.0, close=99.5, vol=1000.0)

        state = detect_market_state(candles_4h, candles_1h)
        self.assertEqual(state.state, "Trending")
        self.assertAlmostEqual(state.w_trend, 0.60)

    def test_normal_state_with_flat_price(self):
        # Flat price → ADX near 0, normal volume → Normal state
        candles_4h = make_candles(200, high=100.5, low=99.5, close=100.0, vol=1000.0)
        candles_1h = make_candles(200, high=100.5, low=99.5, close=100.0, vol=1000.0)

        state = detect_market_state(candles_4h, candles_1h)
        # ADX < 20 on flat series → could be Ranging or Normal; either way not Low Liquidity
        self.assertNotEqual(state.state, "Low Liquidity")
        # Weight sum must equal 1 for non-low-liquidity states
        self.assertAlmostEqual(
            state.w_trend + state.w_vol + state.w_osc, 1.0, places=6
        )

    def test_low_liquidity_state(self):
        # vol_cur / vol_ma20 must be < 0.5 to trigger Low Liquidity.
        # sma(vol1, 20) uses the last-20 values.
        # Strategy: 199 candles with vol=10000, final candle with vol=1
        # → vol_ma20 ≈ (10000×19 + 1)/20 ≈ 9500 and vol_cur=1 → ratio ≈ 0.0001 < 0.5
        candles_4h = make_candles(200, high=100.5, low=99.5, close=100.0, vol=1000.0)
        candles_1h = (
            [Candle(ts=i, open=100.0, high=100.5, low=99.5, close=100.0, vol=10000.0, confirm="1")
             for i in range(199)]
            + [Candle(ts=199, open=100.0, high=100.5, low=99.5, close=100.0, vol=1.0, confirm="1")]
        )
        state = detect_market_state(candles_4h, candles_1h)
        self.assertEqual(state.state, "Low Liquidity")

    def test_weight_sum_is_one_for_all_non_low_liquidity_states(self):
        # Normal
        candles_4h = make_candles(200, high=100.5, low=99.5, close=100.0, vol=1000.0)
        candles_1h = make_candles(200, high=100.5, low=99.5, close=100.0, vol=1000.0)
        state = detect_market_state(candles_4h, candles_1h)
        if state.state != "Low Liquidity":
            self.assertAlmostEqual(
                state.w_trend + state.w_vol + state.w_osc, 1.0, places=6
            )

        # Trending
        n = 200
        candles_4h_trend = [
            Candle(ts=i, open=100.0 + i * 0.5, high=100.0 + i * 0.5 + 1.0,
                   low=100.0 + i * 0.5 - 1.0, close=100.0 + i * 0.5,
                   vol=1000.0, confirm="1")
            for i in range(n)
        ]
        state_trend = detect_market_state(candles_4h_trend, candles_1h)
        if state_trend.state != "Low Liquidity":
            self.assertAlmostEqual(
                state_trend.w_trend + state_trend.w_vol + state_trend.w_osc, 1.0, places=6
            )


if __name__ == "__main__":
    unittest.main()
