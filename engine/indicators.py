"""
engine/indicators.py — Pure technical indicator functions.

All functions operate on plain Python lists (no third-party deps).
No I/O, no side effects — safe to unit-test in isolation.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Moving Averages
# ─────────────────────────────────────────────────────────────────────────────

def ema_list(series: List[float], n: int) -> List[Optional[float]]:
    """
    Exponential Moving Average series.
    EMAᵢ = closeᵢ × k + EMAᵢ₋₁ × (1−k),  k = 2/(n+1).
    Returns a list of the same length; first n-1 values are None.
    """
    out: List[Optional[float]] = [None] * len(series)
    if len(series) < n:
        return out
    k = 2 / (n + 1)
    out[n - 1] = sum(series[:n]) / n
    for i in range(n, len(series)):
        out[i] = series[i] * k + out[i - 1] * (1 - k)   # type: ignore[operator]
    return out


def ema_scalar(series: List[float], n: int) -> Optional[float]:
    """Return only the last EMA value (scalar convenience wrapper)."""
    vals = ema_list(series, n)
    return vals[-1] if vals else None


def sma(series: List[float], n: int) -> Optional[float]:
    """Simple moving average of the last *n* values."""
    if len(series) < n:
        return None
    return sum(series[-n:]) / n


# ─────────────────────────────────────────────────────────────────────────────
# MACD
# ─────────────────────────────────────────────────────────────────────────────

def macd(
    series: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[
    Optional[float],   # macd value (last bar)
    Optional[float],   # signal value
    Optional[float],   # histogram (last)
    Optional[float],   # histogram (prev)
    Optional[float],   # macd value (prev bar)
]:
    """
    MACD(fast, slow, signal).
    Returns (macd_val, signal_val, hist, hist_prev, macd_prev_val).
    All scalars for the last two confirmed candles.
    """
    e_fast = ema_list(series, fast)
    e_slow = ema_list(series, slow)
    mac: List[Optional[float]] = [
        None if a is None or b is None else a - b
        for a, b in zip(e_fast, e_slow)
    ]

    valid_mac = [v for v in mac if v is not None]
    if len(valid_mac) < signal:
        return None, None, None, None, None

    # Build signal EMA over valid MACD values
    k = 2 / (signal + 1)
    seed = sum(valid_mac[:signal]) / signal
    sig_vals = [seed]
    for v in valid_mac[signal:]:
        seed = v * k + seed * (1 - k)
        sig_vals.append(seed)

    # Align signal back to mac list indices
    sig: List[Optional[float]] = [None] * len(mac)
    j = 0
    for i, v in enumerate(mac):
        if v is not None:
            if j >= signal - 1:
                sig[i] = sig_vals[j - (signal - 1)]
            j += 1

    hist_series: List[Optional[float]] = [
        None if mac[i] is None or sig[i] is None else mac[i] - sig[i]   # type: ignore[operator]
        for i in range(len(mac))
    ]

    h_valid = [(i, v) for i, v in enumerate(hist_series) if v is not None]
    if len(h_valid) < 2:
        return mac[-1], sig[-1], None, None, None

    _, h0 = h_valid[-1]
    _, h1 = h_valid[-2]
    return mac[-1], sig[-1], h0, h1, mac[-2] if mac[-2] is not None else None


# ─────────────────────────────────────────────────────────────────────────────
# Bollinger Bands
# ─────────────────────────────────────────────────────────────────────────────

def bollinger_bands(
    series: List[float], n: int = 20, k: float = 2.0
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    BB(n, k): returns (mid, upper, lower).
    Mid = SMA(n); Upper / Lower = Mid ± k × σ (population std-dev).
    """
    if len(series) < n:
        return None, None, None
    window = series[-n:]
    mid = sum(window) / n
    sigma = math.sqrt(sum((x - mid) ** 2 for x in window) / n)
    return mid, mid + k * sigma, mid - k * sigma


# ─────────────────────────────────────────────────────────────────────────────
# RSI
# ─────────────────────────────────────────────────────────────────────────────

def rsi(series: List[float], n: int = 14) -> Optional[float]:
    """
    RSI(n) using Wilder smoothing.
    Returns RSI for the last bar, or None if data is insufficient.
    """
    if len(series) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(series)):
        d = series[i] - series[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_g = sum(gains[:n]) / n
    avg_l = sum(losses[:n]) / n
    for i in range(n, len(gains)):
        avg_g = (avg_g * (n - 1) + gains[i]) / n
        avg_l = (avg_l * (n - 1) + losses[i]) / n
    return 100 - 100 / (1 + avg_g / avg_l) if avg_l else 100.0


# ─────────────────────────────────────────────────────────────────────────────
# KDJ
# ─────────────────────────────────────────────────────────────────────────────

def kdj(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    n: int = 9,
) -> Tuple[float, float, float]:
    """
    KDJ(n, 3, 3) with Wilder smoothing.

    K and D are initialized to 50.0 for the first n-bar window.
    Returns (K, D, J) scalar values.  Returns (50.0, 50.0, 50.0) if data
    is insufficient (len(closes) < n).
    """
    if len(closes) < n:
        return (50.0, 50.0, 50.0)

    K = 50.0
    D = 50.0

    for i in range(n - 1, len(closes)):
        window_high = max(highs[i - n + 1 : i + 1])
        window_low  = min(lows[i  - n + 1 : i + 1])
        if window_high == window_low:
            rsv = 50.0
        else:
            rsv = (closes[i] - window_low) / (window_high - window_low) * 100.0
        # Wilder smoothing: 1/3 weight on new value
        K = (2 / 3) * K + (1 / 3) * rsv
        D = (2 / 3) * D + (1 / 3) * K

    J = 3 * K - 2 * D
    return (round(K, 2), round(D, 2), round(J, 2))


# ─────────────────────────────────────────────────────────────────────────────
# ATR
# ─────────────────────────────────────────────────────────────────────────────

def atr_list(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    n: int,
) -> List[Optional[float]]:
    """
    ATR(n) using EMA of True Range.
    TRᵢ = max(H−L, |H−C_prev|, |L−C_prev|).
    """
    tr: List[float] = []
    for i in range(len(closes)):
        if i == 0:
            tr.append(highs[i] - lows[i])
        else:
            tr.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            ))
    return ema_list(tr, n)


# ─────────────────────────────────────────────────────────────────────────────
# SuperTrend
# ─────────────────────────────────────────────────────────────────────────────

def supertrend(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    n: int = 10,
    multiplier: float = 3.0,
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """
    SuperTrend(n, multiplier).
    Returns (supertrend_series, final_upper_series, final_lower_series).

    Bullish: price > final_lower  (supertrend == final_lower).
    Bearish: price < final_upper  (supertrend == final_upper).
    """
    atr = atr_list(highs, lows, closes, n)
    fu: List[Optional[float]] = [None] * len(closes)
    fl: List[Optional[float]] = [None] * len(closes)
    st: List[Optional[float]] = [None] * len(closes)

    for i in range(len(closes)):
        if atr[i] is None:
            continue
        hl2 = (highs[i] + lows[i]) / 2
        bu = hl2 + multiplier * atr[i]   # type: ignore[operator]
        bl = hl2 - multiplier * atr[i]   # type: ignore[operator]

        if i == 0 or fu[i - 1] is None:
            fu[i] = bu
            fl[i] = bl
        else:
            fu[i] = bu if bu < fu[i - 1] or closes[i - 1] > fu[i - 1] else fu[i - 1]  # type: ignore
            fl[i] = bl if bl > fl[i - 1] or closes[i - 1] < fl[i - 1] else fl[i - 1]  # type: ignore

        if st[i - 1] is None or i == 0:
            st[i] = fu[i] if closes[i] <= fu[i] else fl[i]   # type: ignore
        elif st[i - 1] == fu[i - 1]:
            st[i] = fu[i] if closes[i] <= fu[i] else fl[i]   # type: ignore
        else:
            st[i] = fl[i] if closes[i] >= fl[i] else fu[i]   # type: ignore

    return st, fu, fl


# ─────────────────────────────────────────────────────────────────────────────
# Ichimoku Cloud
# ─────────────────────────────────────────────────────────────────────────────

def ichimoku(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    tenkan_n: int = 9,
    kijun_n: int = 26,
    senkou_b_n: int = 52,
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """
    Ichimoku Cloud (tenkan_n, kijun_n, senkou_b_n).
    Returns (tenkan, kijun, cloud_top, cloud_bottom).

    Cloud values are approximate (non-displaced) for scoring purposes.
    Bullish: close > cloud_top AND tenkan > kijun.
    Bearish: close < cloud_bottom AND tenkan < kijun.
    """
    if len(closes) < senkou_b_n:
        return None, None, None, None
    tenkan = (max(highs[-tenkan_n:]) + min(lows[-tenkan_n:])) / 2
    kijun  = (max(highs[-kijun_n:])  + min(lows[-kijun_n:])) / 2
    span_a = (tenkan + kijun) / 2
    span_b = (max(highs[-senkou_b_n:]) + min(lows[-senkou_b_n:])) / 2
    cloud_top    = max(span_a, span_b)
    cloud_bottom = min(span_a, span_b)
    return tenkan, kijun, cloud_top, cloud_bottom


# ─────────────────────────────────────────────────────────────────────────────
# ADX
# ─────────────────────────────────────────────────────────────────────────────

def adx(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    n: int = 14,
) -> Optional[float]:
    """
    ADX(n) using Wilder smoothing.
    Returns scalar ADX value, or None if data is insufficient.

    ADX > 25 → Trending; ADX < 20 → Ranging.
    """
    if len(closes) < n * 2 + 1:
        return None
    pdm_l: List[float] = []
    ndm_l: List[float] = []
    tr_l:  List[float] = []
    for i in range(1, len(closes)):
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        pdm_l.append(up if up > dn and up > 0 else 0)
        ndm_l.append(dn if dn > up and dn > 0 else 0)
        tr_l.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))

    def _wilder(s: List[float], period: int) -> List[float]:
        result = [sum(s[:period])]
        for v in s[period:]:
            result.append(result[-1] - result[-1] / period + v)
        return result

    atr_w = _wilder(tr_l, n)
    pdm_w = _wilder(pdm_l, n)
    ndm_w = _wilder(ndm_l, n)

    dx_vals: List[float] = []
    for a, p, nm in zip(atr_w, pdm_w, ndm_w):
        pdi = 100 * p / a if a else 0
        ndi = 100 * nm / a if a else 0
        denom = pdi + ndi
        dx_vals.append(abs(pdi - ndi) / denom * 100 if denom else 0)

    if len(dx_vals) < n:
        return None
    adx_val = sum(dx_vals[:n]) / n
    for v in dx_vals[n:]:
        adx_val = (adx_val * (n - 1) + v) / n
    return adx_val
