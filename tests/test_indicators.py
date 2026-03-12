"""
tests/test_indicators.py — Unit tests for engine/indicators.py.

All functions are pure Python with no I/O; no mocking is needed.
"""
import math
import unittest

from engine.indicators import (
    ema_list, ema_scalar, sma,
    macd, bollinger_bands, rsi, kdj,
    atr_list, supertrend, ichimoku, adx,
)


# ─────────────────────────────────────────────────────────────────────────────
# EMA
# ─────────────────────────────────────────────────────────────────────────────

class TestEmaList(unittest.TestCase):

    def test_shorter_than_n_returns_all_none(self):
        result = ema_list([1.0, 2.0], 5)
        self.assertEqual(result, [None, None])

    def test_basic_ema_values(self):
        # ema_list([1,2,3,4,5], 3):
        #   k = 2/(3+1) = 0.5
        #   seed (index 2) = (1+2+3)/3 = 2.0
        #   index 3: 4*0.5 + 2.0*0.5 = 3.0
        #   index 4: 5*0.5 + 3.0*0.5 = 4.0
        result = ema_list([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])
        self.assertAlmostEqual(result[2], 2.0)
        self.assertAlmostEqual(result[3], 3.0)
        self.assertAlmostEqual(result[4], 4.0)

    def test_length_preserved(self):
        series = list(range(1, 11))
        result = ema_list(series, 3)
        self.assertEqual(len(result), len(series))


class TestEmaScalar(unittest.TestCase):

    def test_returns_last_value(self):
        series = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.assertAlmostEqual(ema_scalar(series, 3), ema_list(series, 3)[-1])

    def test_insufficient_data_returns_none(self):
        self.assertIsNone(ema_scalar([1.0, 2.0], 5))


# ─────────────────────────────────────────────────────────────────────────────
# SMA
# ─────────────────────────────────────────────────────────────────────────────

class TestSma(unittest.TestCase):

    def test_basic(self):
        self.assertAlmostEqual(sma([1.0, 2.0, 3.0, 4.0, 5.0], 3), 4.0)

    def test_insufficient_data_returns_none(self):
        self.assertIsNone(sma([1.0, 2.0], 5))


# ─────────────────────────────────────────────────────────────────────────────
# MACD
# ─────────────────────────────────────────────────────────────────────────────

class TestMacd(unittest.TestCase):

    def test_insufficient_data_returns_all_none(self):
        short = [float(i) for i in range(30)]
        m, s, h, hp, mp = macd(short)
        self.assertIsNone(m)
        self.assertIsNone(s)
        self.assertIsNone(h)
        self.assertIsNone(hp)
        self.assertIsNone(mp)

    def test_sufficient_data_returns_non_none(self):
        series = [float(i) + 100 for i in range(60)]
        m, s, h, hp, mp = macd(series)
        self.assertIsNotNone(m)
        self.assertIsNotNone(s)
        self.assertIsNotNone(h)

    def test_histogram_sign(self):
        # histogram = macd_val - signal_val
        series = [float(i) + 100 for i in range(60)]
        m, s, h, hp, _ = macd(series)
        if m is not None and s is not None and h is not None:
            self.assertAlmostEqual(h, m - s, places=6)


# ─────────────────────────────────────────────────────────────────────────────
# RSI
# ─────────────────────────────────────────────────────────────────────────────

class TestRsi(unittest.TestCase):

    def test_insufficient_data_returns_none(self):
        self.assertIsNone(rsi([1.0] * 14))

    def test_all_gains_approaches_100(self):
        series = [float(i) for i in range(1, 30)]
        result = rsi(series)
        self.assertIsNotNone(result)
        self.assertGreater(result, 90.0)

    def test_all_losses_approaches_0(self):
        series = [float(i) for i in range(29, 0, -1)]
        result = rsi(series)
        self.assertIsNotNone(result)
        self.assertLess(result, 10.0)

    def test_alternating_near_50(self):
        series = []
        for i in range(30):
            series.append(100.0 + (1.0 if i % 2 == 0 else -1.0))
        result = rsi(series)
        self.assertIsNotNone(result)
        self.assertGreater(result, 30.0)
        self.assertLess(result, 70.0)


# ─────────────────────────────────────────────────────────────────────────────
# Bollinger Bands
# ─────────────────────────────────────────────────────────────────────────────

class TestBollingerBands(unittest.TestCase):

    def test_insufficient_data_returns_triple_none(self):
        self.assertEqual(bollinger_bands([1.0] * 10), (None, None, None))

    def test_constant_series_upper_eq_lower(self):
        series = [50.0] * 20
        mid, upper, lower = bollinger_bands(series)
        self.assertAlmostEqual(upper, lower)
        self.assertAlmostEqual(mid, 50.0)

    def test_known_series(self):
        series = [float(i) for i in range(1, 21)]  # 1..20
        mid, upper, lower = bollinger_bands(series)
        expected_mid = sum(range(1, 21)) / 20
        self.assertAlmostEqual(mid, expected_mid)
        # sigma (population)
        variance = sum((x - expected_mid) ** 2 for x in range(1, 21)) / 20
        sigma = math.sqrt(variance)
        self.assertAlmostEqual(upper, expected_mid + 2 * sigma, places=6)
        self.assertAlmostEqual(lower, expected_mid - 2 * sigma, places=6)


# ─────────────────────────────────────────────────────────────────────────────
# KDJ
# ─────────────────────────────────────────────────────────────────────────────

class TestKdj(unittest.TestCase):

    def test_insufficient_data_returns_50_50_50(self):
        highs  = [10.0] * 5
        lows   = [8.0]  * 5
        closes = [9.0]  * 5
        k, d, j = kdj(highs, lows, closes, n=9)
        self.assertEqual(k, 50.0)
        self.assertEqual(d, 50.0)
        self.assertEqual(j, 50.0)

    def test_constant_series_stays_at_50(self):
        # constant price → RSV=50 always → K stays at 50, D stays at 50
        n = 20
        highs  = [100.0] * n
        lows   = [100.0] * n
        closes = [100.0] * n
        k, d, j = kdj(highs, lows, closes)
        self.assertAlmostEqual(k, 50.0, places=4)
        self.assertAlmostEqual(d, 50.0, places=4)
        self.assertAlmostEqual(j, 50.0, places=4)


# ─────────────────────────────────────────────────────────────────────────────
# ATR
# ─────────────────────────────────────────────────────────────────────────────

class TestAtrList(unittest.TestCase):

    def test_single_bar_returns_all_none_for_n2(self):
        result = atr_list([10.0], [8.0], [9.0], 2)
        self.assertEqual(result, [None])

    def test_constant_bars_atr_near_range(self):
        # H=10, L=8, C=9 for all bars → TR=2 every bar → ATR → 2
        n_bars = 30
        highs  = [10.0] * n_bars
        lows   = [8.0]  * n_bars
        closes = [9.0]  * n_bars
        result = atr_list(highs, lows, closes, 14)
        valid = [v for v in result if v is not None]
        self.assertTrue(len(valid) > 0)
        self.assertAlmostEqual(valid[-1], 2.0, places=4)


# ─────────────────────────────────────────────────────────────────────────────
# SuperTrend
# ─────────────────────────────────────────────────────────────────────────────

class TestSupertrend(unittest.TestCase):

    def _make_series(self, n, base, step):
        closes = [base + i * step for i in range(n)]
        highs  = [c + 1.0 for c in closes]
        lows   = [c - 1.0 for c in closes]
        return highs, lows, closes

    def test_returns_three_lists_same_length(self):
        h, l, c = self._make_series(50, 100, 0.5)
        st, fu, fl = supertrend(h, l, c)
        self.assertEqual(len(st), 50)
        self.assertEqual(len(fu), 50)
        self.assertEqual(len(fl), 50)

    def test_uptrend_final_lower_band_below_close(self):
        h, l, c = self._make_series(60, 100, 1.0)
        _, _, fl = supertrend(h, l, c)
        valid_fl = [v for v in fl if v is not None]
        self.assertTrue(len(valid_fl) > 0)
        self.assertLess(valid_fl[-1], c[-1])

    def test_downtrend_final_upper_band_above_close(self):
        h, l, c = self._make_series(60, 200, -1.0)
        _, fu, _ = supertrend(h, l, c)
        valid_fu = [v for v in fu if v is not None]
        self.assertTrue(len(valid_fu) > 0)
        self.assertGreater(valid_fu[-1], c[-1])


# ─────────────────────────────────────────────────────────────────────────────
# Ichimoku
# ─────────────────────────────────────────────────────────────────────────────

class TestIchimoku(unittest.TestCase):

    def test_insufficient_data_returns_quad_none(self):
        highs  = [100.0] * 30
        lows   = [99.0]  * 30
        closes = [99.5]  * 30
        self.assertEqual(ichimoku(highs, lows, closes), (None, None, None, None))

    def test_sufficient_data_returns_non_none(self):
        n = 60
        highs  = [100.0 + i * 0.1 for i in range(n)]
        lows   = [99.0  + i * 0.1 for i in range(n)]
        closes = [99.5  + i * 0.1 for i in range(n)]
        t, k, ct, cb = ichimoku(highs, lows, closes)
        self.assertIsNotNone(t)
        self.assertIsNotNone(k)
        self.assertIsNotNone(ct)
        self.assertIsNotNone(cb)


# ─────────────────────────────────────────────────────────────────────────────
# ADX
# ─────────────────────────────────────────────────────────────────────────────

class TestAdx(unittest.TestCase):

    def test_insufficient_data_returns_none(self):
        highs  = [100.0] * 20
        lows   = [99.0]  * 20
        closes = [99.5]  * 20
        self.assertIsNone(adx(highs, lows, closes))

    def test_strongly_trending_series_adx_above_25(self):
        n = 100
        closes = [100.0 + i * 2.0 for i in range(n)]
        highs  = [c + 1.0 for c in closes]
        lows   = [c - 1.0 for c in closes]
        result = adx(highs, lows, closes)
        self.assertIsNotNone(result)
        self.assertGreater(result, 25.0)

    def test_flat_series_adx_near_0(self):
        n = 60
        closes = [100.0] * n
        highs  = [100.5] * n
        lows   = [99.5]  * n
        result = adx(highs, lows, closes)
        self.assertIsNotNone(result)
        self.assertLess(result, 5.0)


if __name__ == "__main__":
    unittest.main()
