"""
tests/test_normalize.py — Unit tests for engine.signals._normalize_group
and engine.signals._consecutive_streak.
"""
import unittest

from engine.signals import _normalize_group, _consecutive_streak
from engine.models import SignalResult


def _make_signal(sign, conf):
    """Helper to build a minimal SignalResult."""
    return SignalResult(
        name="test", raw_value="x", condition="c",
        sign=sign, confidence=conf, vote=sign * conf,
    )


class TestNormalizeGroup(unittest.TestCase):

    def test_empty_list_returns_zero(self):
        self.assertEqual(_normalize_group([], 5), 0.0)

    def test_all_bullish_full_confidence(self):
        signals = [_make_signal(+1, 1.0) for _ in range(5)]
        self.assertAlmostEqual(_normalize_group(signals, 5), +5.0)

    def test_all_bearish_full_confidence(self):
        signals = [_make_signal(-1, 1.0) for _ in range(5)]
        self.assertAlmostEqual(_normalize_group(signals, 5), -5.0)

    def test_mixed_three_bull_two_bear(self):
        signals = (
            [_make_signal(+1, 1.0) for _ in range(3)]
            + [_make_signal(-1, 1.0) for _ in range(2)]
        )
        # raw = 3 - 2 = 1; (1/5)*5 = 1.0
        self.assertAlmostEqual(_normalize_group(signals, 5), +1.0)

    def test_partial_confidence(self):
        signals = [_make_signal(+1, 0.5) for _ in range(5)]
        # raw = 2.5; (2.5/5)*5 = 2.5
        self.assertAlmostEqual(_normalize_group(signals, 5), +2.5)

    def test_n_zero_returns_zero_no_error(self):
        signals = [_make_signal(+1, 1.0)]
        self.assertEqual(_normalize_group(signals, 0), 0.0)


class TestConsecutiveStreak(unittest.TestCase):

    def test_all_above(self):
        values    = [1.0, 2.0, 3.0]
        reference = [0.0, 1.0, 2.0]
        self.assertEqual(_consecutive_streak(values, reference, above=True), 3)

    def test_last_fails_streak_zero(self):
        # values[2]=1 is NOT > reference[2]=2 → breaks immediately
        values    = [1.0, 2.0, 1.0]
        reference = [0.0, 1.0, 2.0]
        self.assertEqual(_consecutive_streak(values, reference, above=True), 0)

    def test_none_in_reference_stops_streak(self):
        values    = [1.0, 2.0, 3.0]
        reference = [0.0, 1.0, None]
        self.assertEqual(_consecutive_streak(values, reference, above=True), 0)

    def test_all_below_above_false(self):
        values    = [2.0, 1.0, 0.0]
        reference = [3.0, 2.0, 1.0]
        self.assertEqual(_consecutive_streak(values, reference, above=False), 3)

    def test_reference_shorter_than_values(self):
        # i >= len(reference) guard must prevent IndexError
        values    = [1.0, 2.0, 3.0, 4.0]
        reference = [0.0, 1.0]   # shorter
        # i=3 → 3 >= 2 → break → streak = 0
        self.assertEqual(_consecutive_streak(values, reference, above=True), 0)


if __name__ == "__main__":
    unittest.main()
