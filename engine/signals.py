"""
engine/signals.py — Core SignalEngine: scoring helpers + SignalEngine class.

Depends on: models, indicators, market_state.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from .models import (
    MarketData, MarketState, SignalResult, GroupScore, Report,
)
from .indicators import (
    ema_list, ema_scalar, sma, macd, bollinger_bands,
    rsi, kdj, atr_list, supertrend, ichimoku,
)
from .market_state import detect_market_state


# ─────────────────────────────────────────────────────────────────────────────
# Scoring helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mk(name: str, raw: str, cond: str, sign: int, conf: float) -> SignalResult:
    """Construct a SignalResult with vote = sign × confidence."""
    return SignalResult(
        name=name, raw_value=raw, condition=cond,
        sign=sign, confidence=conf, vote=sign * conf,
    )


def _normalize_group(signals: List[SignalResult], n: int) -> float:
    """Normalize Σ(sign × confidence) → [−5, +5] with group size N."""
    raw = sum(s.vote for s in signals)
    return (raw / n) * 5 if n else 0.0


def _consecutive_streak(values: List[float], reference: List[Optional[float]], above: bool) -> int:
    """
    Count consecutive entries from the end of `values` where
    values[i] > reference[i] (if above=True) or values[i] < reference[i] (if above=False).
    Stops at the first candle that breaks the condition or where reference[i] is None.
    """
    streak = 0
    for i in range(len(values) - 1, -1, -1):
        if reference[i] is None:
            break
        if above and values[i] > reference[i]:
            streak += 1
        elif not above and values[i] < reference[i]:
            streak += 1
        else:
            break
    return streak


# ─────────────────────────────────────────────────────────────────────────────
# SignalEngine
# ─────────────────────────────────────────────────────────────────────────────

class SignalEngine:
    """
    Compute all signals from MarketData and produce a Report.

    Parameters
    ----------
    data         : MarketData  — output of fetcher.fetch_all()
    account_size : float       — total account in USDT (position sizing)
    is_swap      : bool        — False → skip funding-rate and OI signals
    """

    def __init__(
        self,
        data: MarketData,
        account_size: float = 10_000.0,
        is_swap: bool = True,
    ) -> None:
        self.data    = data
        self.account = account_size
        self.is_swap = is_swap

        # Shorthand arrays (confirmed candles only)
        c4 = data.candles_4h
        c1 = data.candles_1h
        c15 = data.candles_15m
        self.h4 = [c.high  for c in c4];  self.l4 = [c.low   for c in c4]
        self.c4 = [c.close for c in c4];  self.o4 = [c.open  for c in c4]
        self.v4 = [c.vol   for c in c4]
        self.h1 = [c.high  for c in c1];  self.l1 = [c.low   for c in c1]
        self.c1 = [c.close for c in c1];  self.o1 = [c.open  for c in c1]
        self.v1 = [c.vol   for c in c1]
        self.h15 = [c.high  for c in c15]
        self.l15 = [c.low   for c in c15]
        self.c15 = [c.close for c in c15]

    # ── Trend signals (5) ────────────────────────────────────────────────────

    def _sig_ema(self) -> SignalResult:
        """EMA(9)/EMA(21) crossover on 4H."""
        e9  = ema_list(self.c4, 9)
        e21 = ema_list(self.c4, 21)
        if e9[-1] is None or e21[-1] is None:
            return _mk("EMA 4H", "N/A", "Insufficient data", 0, 0.0)

        consec = 0
        for i in range(len(e9) - 1, -1, -1):
            if e9[i] is None or e21[i] is None:
                break
            if e9[i] > e21[i]:
                consec += 1
            else:
                break

        bear_consec = 0
        for i in range(len(e9) - 1, -1, -1):
            if e9[i] is None or e21[i] is None:
                break
            if e9[i] < e21[i]:
                bear_consec += 1
            else:
                break

        raw = f"EMA9={e9[-1]:,.0f} EMA21={e21[-1]:,.0f}"
        if e9[-1] > e21[-1]:
            conf = 1.0 if consec >= 3 else (0.75 if consec == 2 else 0.5)
            cond = f"EMA9 > EMA21 ({consec} candles confirmed)"
            return _mk("EMA Cross 4H", raw, cond, +1, conf)
        else:
            conf = 1.0 if bear_consec >= 3 else (0.75 if bear_consec == 2 else 0.5)
            cond = f"EMA9 < EMA21 ({bear_consec} candles confirmed)"
            return _mk("EMA Cross 4H", raw, cond, -1, conf)

    def _sig_macd(self) -> SignalResult:
        """MACD(12,26,9) on 4H."""
        mac_val, sig_val, h0, h1, _ = macd(self.c4)
        if mac_val is None or sig_val is None or h0 is None or h1 is None:
            return _mk("MACD 4H", "N/A", "Insufficient data", 0, 0.0)
        raw = f"MACD={mac_val:.2f} Sig={sig_val:.2f} Hist[0]={h0:.2f} Hist[-1]={h1:.2f}"
        if mac_val > sig_val and h0 > h1:
            cross = mac_val * h1 < 0
            conf = 0.5 if cross else (0.75 if (h0 - h1) / abs(h1 + 1e-9) < 0.3 else 1.0)
            return _mk("MACD 4H", raw, "MACD > Signal, hist expanding → bullish", +1, conf)
        elif mac_val < sig_val and h0 < h1:
            cross = mac_val * h1 > 0
            conf = 0.5 if cross else (0.75 if (h1 - h0) / abs(h1 + 1e-9) < 0.3 else 1.0)
            return _mk("MACD 4H", raw, "MACD < Signal, hist expanding down → bearish", -1, conf)
        return _mk("MACD 4H", raw, "No clear expansion", 0, 0.0)

    def _sig_supertrend(self) -> SignalResult:
        """SuperTrend(10, 3) on 4H."""
        st, fu, fl = supertrend(self.h4, self.l4, self.c4)
        if st[-1] is None:
            return _mk("SuperTrend 4H", "N/A", "Insufficient data", 0, 0.0)
        close = self.c4[-1]
        raw = (f"Close={close:,.2f} ST={st[-1]:,.2f} "
               f"FinalLower={fl[-1]:,.2f} FinalUpper={fu[-1]:,.2f}")
        if close > fl[-1]:  # type: ignore[operator]
            bullish_streak = _consecutive_streak(self.c4, fl, above=True)
            conf = 1.0 if bullish_streak >= 3 else (0.75 if bullish_streak == 2 else 0.5)
            return _mk("SuperTrend 4H", raw,
                       f"Price > lower band ({bullish_streak} bars) → bullish", +1, conf)
        else:
            bearish_streak = _consecutive_streak(self.c4, fu, above=False)
            conf = 1.0 if bearish_streak >= 3 else (0.75 if bearish_streak == 2 else 0.5)
            return _mk("SuperTrend 4H", raw,
                       f"Price < upper band ({bearish_streak} bars) → bearish", -1, conf)

    def _sig_bb(self) -> SignalResult:
        """Bollinger Band(20, 2) on 4H — wick-reversion signal."""
        mid, up, low = bollinger_bands(self.c4)
        if mid is None:
            return _mk("BB 4H", "N/A", "Insufficient data", 0, 0.0)
        h, l, c = self.h4[-1], self.l4[-1], self.c4[-1]
        raw = f"Close={c:,.2f} Upper={up:,.2f} Mid={mid:,.2f} Lower={low:,.2f}"
        if l <= low and c > low:  # type: ignore[operator]
            conf = 1.0 if c < low else 0.7
            return _mk("BB 4H", raw, "Wick to lower band, close above → bullish", +1, conf)
        elif h >= up and c < up:  # type: ignore[operator]
            conf = 1.0 if c > up else 0.7
            return _mk("BB 4H", raw, "Wick to upper band, close below → bearish", -1, conf)
        elif c > mid:
            return _mk("BB 4H", raw, "Price above mid, inside bands → mild bullish", +1, 0.4)
        else:
            return _mk("BB 4H", raw, "Price below mid, inside bands → mild bearish", -1, 0.4)

    def _sig_ichimoku(self) -> SignalResult:
        """Ichimoku Cloud(9, 26, 52) on 4H."""
        tenkan, kijun, cloud_top, cloud_bot = ichimoku(self.h4, self.l4, self.c4)
        if tenkan is None:
            return _mk("Ichimoku 4H", "N/A",
                       "Insufficient data (need 52+ candles)", 0, 0.0)
        close = self.c4[-1]
        raw = (f"Close={close:,.2f} Tenkan={tenkan:,.2f} Kijun={kijun:,.2f} "
               f"CloudTop={cloud_top:,.2f} CloudBot={cloud_bot:,.2f}")
        if close > cloud_top and tenkan > kijun:
            return _mk("Ichimoku 4H", raw,
                       "Price above cloud, TK bullish cross → bullish", +1, 1.0)
        elif close < cloud_bot and tenkan < kijun:
            return _mk("Ichimoku 4H", raw,
                       "Price below cloud, TK bearish cross → bearish", -1, 1.0)
        elif close > cloud_top:
            return _mk("Ichimoku 4H", raw,
                       "Price above cloud but TK mixed → mild bullish", +1, 0.5)
        elif close < cloud_bot:
            return _mk("Ichimoku 4H", raw,
                       "Price below cloud but TK mixed → mild bearish", -1, 0.5)
        return _mk("Ichimoku 4H", raw, "Price inside cloud → neutral", 0, 0.0)

    # ── Volume & Sentiment signals (5) ───────────────────────────────────────

    def _sig_volume_breakout(self) -> SignalResult:
        """1H volume vs MA(20) breakout signal."""
        vol_ma  = sma(self.v1, 20)
        vol_cur = self.v1[-1]
        if vol_ma is None:
            return _mk("Vol Breakout 1H", "N/A", "Insufficient data", 0, 0.0)
        ratio = vol_cur / vol_ma
        raw = f"Vol={vol_cur:,.0f} MA20={vol_ma:,.0f} ratio={ratio:.2f}x"
        if ratio > 2.0:
            if self.c1[-1] > self.o1[-1]:
                return _mk("Vol Breakout 1H", raw,
                           f"Vol {ratio:.1f}× MA20 + up candle → bullish breakout", +1, 1.0)
            else:
                return _mk("Vol Breakout 1H", raw,
                           f"Vol {ratio:.1f}× MA20 + down candle → bearish breakout", -1, 1.0)
        elif ratio >= 1.5:
            if self.c1[-1] > self.o1[-1]:
                return _mk("Vol Breakout 1H", raw,
                           f"Vol {ratio:.1f}× MA20 + up candle → mild bullish", +1, 0.6)
            else:
                return _mk("Vol Breakout 1H", raw,
                           f"Vol {ratio:.1f}× MA20 + down candle → mild bearish", -1, 0.6)
        elif ratio < 0.5:
            return _mk("Vol Breakout 1H", raw, "Low volume (<0.5× MA20) → LOW CONFIDENCE", 0, 0.0)
        return _mk("Vol Breakout 1H", raw, "Normal volume → neutral", 0, 0.0)

    def _sig_funding(self) -> SignalResult:
        """Funding rate contrarian signal (SWAP only)."""
        if not self.is_swap:
            return _mk("Funding Rate", "N/A", "Spot — skipped", 0, 0.0)
        fr_pct = self.data.funding_rate * 100
        raw = f"FundingRate={fr_pct:.4f}%"
        if fr_pct < -0.01:
            conf = 1.0 if fr_pct < -0.1 else (0.75 if fr_pct < -0.05 else 0.4)
            return _mk("Funding Rate", raw, "Negative funding → contrarian LONG", +1, conf)
        elif fr_pct > 0.05:
            conf = 1.0 if fr_pct > 0.1 else 0.75
            return _mk("Funding Rate", raw, "High positive funding → contrarian SHORT", -1, conf)
        return _mk("Funding Rate", raw, "Neutral funding range", 0, 0.0)

    def _sig_oi(self) -> SignalResult:
        """OI vs OI_MA5 + price direction signal (SWAP only)."""
        if not self.is_swap or self.data.open_interest == 0:
            return _mk("OI Change", "N/A", "Spot or data unavailable — skipped", 0, 0.0)
        oi   = self.data.open_interest
        hist = self.data.oi_history
        oi_ma5      = sum(hist[-5:]) / min(len(hist), 5) if hist else oi
        oi_above_ma5 = oi > oi_ma5
        price_up    = self.c1[-1] > self.c1[-2] if len(self.c1) >= 2 else None
        raw = (f"OI={oi:,.0f} OI_MA5={oi_ma5:,.0f} "
               f"oi>MA5={'Y' if oi_above_ma5 else 'N'} "
               f"price={'up' if price_up else 'down'}")
        if price_up is None:
            return _mk("OI Change", raw, "Insufficient 1H data", 0, 0.0)
        if not oi_above_ma5:
            return _mk("OI Change", raw, "OI ≤ MA5 → conviction weak → neutral", 0, 0.0)
        if price_up:
            return _mk("OI Change", raw, "OI > MA5 + price up → bullish continuation", +1, 1.0)
        else:
            return _mk("OI Change", raw, "OI > MA5 + price down → bearish continuation", -1, 1.0)

    def _sig_orderbook(self) -> SignalResult:
        """Orderbook top-10 bid vs ask depth."""
        bsum = sum(p * sz for p, sz in self.data.bids_top10)
        asum = sum(p * sz for p, sz in self.data.asks_top10)
        if bsum == 0 and asum == 0:
            return _mk("OrderBook", "N/A", "No data", 0, 0.0)
        ratio = bsum / asum if asum else float('inf')
        raw = f"Bids={bsum:,.0f} Asks={asum:,.0f} ratio={ratio:.3f}"
        if ratio > 1.2:
            return _mk("OrderBook", raw, "Bid depth > ask depth × 1.2 → bullish", +1, 1.0)
        elif ratio < 1 / 1.2:
            return _mk("OrderBook", raw, "Ask depth > bid depth × 1.2 → bearish", -1, 1.0)
        return _mk("OrderBook", raw, "Balanced book → neutral", 0, 0.0)

    def _sig_trade_flow(self) -> SignalResult:
        """Buy/sell count from last 50 trades."""
        buys  = sum(1 for t in self.data.trades if t.get("side", "").lower() == "buy")
        sells = sum(1 for t in self.data.trades if t.get("side", "").lower() == "sell")
        total = buys + sells
        if total == 0:
            return _mk("Trade Flow", "N/A", "No trades", 0, 0.0)
        buy_ratio = buys / total
        raw = f"Buys={buys} Sells={sells} buy_ratio={buy_ratio:.2f}"
        if buy_ratio > 0.6:
            return _mk("Trade Flow", raw, "Buy dominant (>60%) → bullish", +1, 1.0)
        elif buy_ratio < 0.4:
            return _mk("Trade Flow", raw, "Sell dominant (>60%) → bearish", -1, 1.0)
        return _mk("Trade Flow", raw, "Balanced flow → neutral", 0, 0.0)

    def _sig_liquidation(self) -> Tuple[SignalResult, List[str]]:
        """
        Liquidation Heatmap — last 100 filled forced liquidations.

        Returns (SignalResult, list_of_detail_notes).
        """
        liqs  = self.data.liquidations
        notes: List[str] = []
        if not liqs:
            notes.append(
                "Liquidation: no recent filled liquidations "
                "(market stable or data unavailable)"
            )
            return _mk("Liquidation", "N/A",
                       "No recent liquidations → neutral", 0, 0.0), notes

        long_liq_usd  = 0.0
        short_liq_usd = 0.0
        prices: List[float] = []

        for liq in liqs:
            details = liq.get("details", [])
            if not isinstance(details, list):
                details = [liq]
            for d in details:
                try:
                    sz   = float(d.get("sz",  0))
                    bk   = float(d.get("bkPx", d.get("px", 0)))
                    side = str(d.get("side", "")).lower()
                    usd  = sz * bk
                    if side == "buy":
                        long_liq_usd  += usd
                    elif side == "sell":
                        short_liq_usd += usd
                    if bk:
                        prices.append(bk)
                except (TypeError, ValueError):
                    continue

        total_usd = long_liq_usd + short_liq_usd
        if total_usd == 0:
            notes.append(
                "Liquidation: orders found but no size/price data parseable"
            )
            return _mk("Liquidation", "N/A",
                       "No parseable liq data → neutral", 0, 0.0), notes

        long_pct  = long_liq_usd  / total_usd * 100
        short_pct = short_liq_usd / total_usd * 100
        raw = (
            f"LongLiq={long_liq_usd:,.0f}USD ({long_pct:.0f}%) "
            f"ShortLiq={short_liq_usd:,.0f}USD ({short_pct:.0f}%) "
            f"Count={len(liqs)}"
        )

        if prices:
            liq_min = min(prices)
            liq_max = max(prices)
            liq_mid = sum(prices) / len(prices)
            notes.append(
                f"Liq price range: {liq_min:,.2f} – {liq_max:,.2f}, avg={liq_mid:,.2f}"
            )
            cur = self.data.last_price
            if cur > liq_mid:
                notes.append(
                    f"Price ({cur:,.2f}) above liq cluster avg → cluster acts as support"
                )
            else:
                notes.append(
                    f"Price ({cur:,.2f}) below liq cluster avg → cluster acts as resistance"
                )

        if long_pct > 70:
            conf = 1.0 if long_pct > 85 else 0.75
            sig  = _mk("Liquidation", raw,
                       f"Long liq dominant ({long_pct:.0f}%) → bearish cascade risk", -1, conf)
        elif short_pct > 70:
            conf = 1.0 if short_pct > 85 else 0.75
            sig  = _mk("Liquidation", raw,
                       f"Short liq dominant ({short_pct:.0f}%) → short squeeze → bullish", +1, conf)
        else:
            sig  = _mk("Liquidation", raw,
                       f"Mixed liquidations (long {long_pct:.0f}% / short {short_pct:.0f}%) → neutral",
                       0, 0.0)

        return sig, notes

    # ── Supplementary signals (RSI, KDJ) ─────────────────────────────────────

    def _supplementary(self) -> List[str]:
        """Return human-readable RSI and KDJ notes (not scored)."""
        notes: List[str] = []
        rsi4h = rsi(self.c4)
        rsi1h = rsi(self.c1)
        k, d, j = kdj(self.h4, self.l4, self.c4)
        if rsi4h is not None:
            tag = ("oversold" if rsi4h < 30 else
                   "overbought" if rsi4h > 70 else "neutral")
            notes.append(f"RSI(14) 4H = {rsi4h:.1f} → {tag}")
        if rsi1h is not None:
            tag = ("oversold" if rsi1h < 30 else
                   "overbought" if rsi1h > 70 else "neutral")
            notes.append(f"RSI(14) 1H = {rsi1h:.1f} → {tag}")
        notes.append(f"KDJ 4H: K={k} D={d} J={j}")
        return notes

    # ── Entry / SL / TP ───────────────────────────────────────────────────────

    def _entry_sl_tp(
        self,
        direction: str,
        ms: MarketState,
    ) -> Tuple[float, float, float, float, float, float, float, float]:
        """
        Compute entry zone, stop-loss and take-profit levels.

        Returns
        -------
        (entry_low, entry_high, entry_mid, sl, sl_pct, tp1, tp2, rr)
        """
        price  = self.data.last_price
        e21_4h = ema_scalar(self.c4, 21) or price
        bb_mid1, bb_up1, bb_low1 = bollinger_bands(self.c1)
        bb_mid1 = bb_mid1 or price
        bb_up1  = bb_up1  or price * 1.02
        bb_low1 = bb_low1 or price * 0.98

        state = ms.state

        if direction == "LONG":
            if state == "Trending":
                el, eh = e21_4h * 0.999, price
            elif state == "Ranging":
                el, eh = bb_low1, bb_mid1
            else:
                el, eh = price * 0.997, price * 1.001
        else:  # SHORT
            if state == "Trending":
                el, eh = price, e21_4h * 1.001
            elif state == "Ranging":
                el, eh = bb_mid1, bb_up1
            else:
                el, eh = price * 0.999, price * 1.003

        entry_mid = (el + eh) / 2

        recent_h = self.h1[-10:] if len(self.h1) >= 10 else self.h1
        recent_l = self.l1[-10:] if len(self.l1) >= 10 else self.l1
        if direction == "LONG":
            sl_raw = min(recent_l) * 0.998
        else:
            sl_raw = max(recent_h) * 1.002

        sl_dist = abs(entry_mid - sl_raw) / entry_mid
        if sl_dist > 0.03:
            sl_raw = entry_mid * (0.97 if direction == "LONG" else 1.03)
        sl = sl_raw

        sl_pct = abs(entry_mid - sl) / entry_mid * 100
        risk   = abs(entry_mid - sl)

        if direction == "LONG":
            tp1 = entry_mid + risk * 1.5
            tp2 = entry_mid + risk * 3.0
        else:
            tp1 = entry_mid - risk * 1.5
            tp2 = entry_mid - risk * 3.0

        rr = 1.5
        return el, eh, entry_mid, sl, sl_pct, tp1, tp2, rr

    def _position_size(
        self,
        entry_mid: float,
        sl: float,
        strength: str,
        ms: MarketState,
    ) -> float:
        """Return risk % of account per signal_skill.md rules."""
        if ms.state == "High Volatility":
            return 0.5
        return 2.0 if strength == "Strong" else 1.0

    # ── Main entry point ──────────────────────────────────────────────────────

    def run(self) -> Report:
        """Compute all signals and return a Report."""
        cot:   List[str] = []
        check: List[str] = []

        # ── Step 1: Market state ─────────────────────────────────────────────
        ms = detect_market_state(self.data.candles_4h, self.data.candles_1h)
        atr_ratio = ms.atr14 / ms.atr_ma10 if ms.atr_ma10 else 1.0
        cot.append(
            f"[MarketState] ADX(14)={ms.adx:.2f} ATR_ratio={atr_ratio:.2f}x "
            f"vol_ratio={ms.vol_ratio:.2f}x → state={ms.state} "
            f"(w_trend={ms.w_trend} w_vol={ms.w_vol} w_osc={ms.w_osc})"
        )
        check.append(
            f"[{'✅' if ms.state != 'Low Liquidity' else '⛔'}] "
            f"Market state classified → {ms.state}"
        )

        if ms.state == "Low Liquidity":
            check.append("[⛔] Low Liquidity — aborting signal computation")
            return Report(
                inst_id=self.data.inst_id,
                price=self.data.last_price,
                timestamp=self.data.timestamp,
                trend=GroupScore("Trend", [], 0, 0),
                volume_senti=GroupScore("Volume/Senti", [], 0, 0),
                oscillator=GroupScore("Oscillator", [], 0, 0),
                total_score=0, direction="NEUTRAL", strength="—",
                market_state="⚠️ LOW CONFIDENCE — Low Liquidity",
                adx_value=ms.adx,
                entry_low=0, entry_high=0, entry_mid=0,
                stop_loss=0, sl_pct=0, tp1=0, tp2=0, rr_ratio=0,
                position_risk_pct=0, position_usdt=0,
                supplementary=[], evidence_bull=[], evidence_bear=[],
                risks=["Low volume detected — signal reliability reduced, skip trade"],
                rr_warning=(
                    "LOW CONFIDENCE: skip trade due to low liquidity"
                ),
                cot_log=cot,
                self_check=check,
            )

        # ── Step 2: Trend signals ─────────────────────────────────────────────
        cot.append("[Trend] Computing 5 trend signals on 4H candles …")
        trend_sigs = [
            self._sig_ema(),
            self._sig_macd(),
            self._sig_supertrend(),
            self._sig_bb(),
            self._sig_ichimoku(),
        ]

        # ── 15m scalp signals (optional, weight 0.5×) ────────────────────────
        scalp_mode = len(self.c15) >= 21
        scalp_sigs: List[SignalResult] = []
        if scalp_mode:
            cot.append("[Scalp/15m] Mode: Scalp (15m active) — adding EMA and RSI on 15m")
            e9_15  = ema_list(self.c15, 9)
            e21_15 = ema_list(self.c15, 21)
            if e9_15[-1] is not None and e21_15[-1] is not None:
                raw_15 = f"EMA9={e9_15[-1]:,.0f} EMA21={e21_15[-1]:,.0f}"
                if e9_15[-1] > e21_15[-1]:
                    scalp_sigs.append(_mk("EMA Cross 15m", raw_15,
                                          "EMA9 > EMA21 → bullish 15m", +1, 0.5))
                else:
                    scalp_sigs.append(_mk("EMA Cross 15m", raw_15,
                                          "EMA9 < EMA21 → bearish 15m", -1, 0.5))
            rsi_15 = rsi(self.c15)
            if rsi_15 is not None:
                raw_r = f"RSI={rsi_15:.1f}"
                if rsi_15 < 30:
                    scalp_sigs.append(_mk("RSI 15m", raw_r,
                                          "Oversold 15m → bullish", +1, 0.5))
                elif rsi_15 > 70:
                    scalp_sigs.append(_mk("RSI 15m", raw_r,
                                          "Overbought 15m → bearish", -1, 0.5))
                else:
                    scalp_sigs.append(_mk("RSI 15m", raw_r,
                                          "Neutral 15m → no signal", 0, 0.0))
            for s in scalp_sigs:
                cot.append(
                    f"  {s.name}: {s.raw_value} → {s.condition} "
                    f"→ score: {s.vote:+.2f} (conf {s.confidence:.2f})"
                )

        all_trend_sigs = trend_sigs + scalp_sigs
        trend_n = len(all_trend_sigs)

        for s in trend_sigs:
            cot.append(
                f"  {s.name}: {s.raw_value} → {s.condition} "
                f"→ score: {s.vote:+.2f} (conf {s.confidence:.2f})"
            )
        trend_norm = _normalize_group(all_trend_sigs, trend_n)
        cot.append(
            f"  Trend raw_sum={sum(s.vote for s in all_trend_sigs):.2f} "
            f"normalized={trend_norm:+.2f}/5"
        )
        check.append(
            f"[{'✅' if all(s.raw_value != 'N/A' for s in trend_sigs) else '⚠️'}] "
            f"All 5 Trend signals computed"
        )

        # ── Step 3: Volume & Sentiment signals ────────────────────────────────
        cot.append("[Vol/Senti] Computing 5 volume/sentiment signals …")
        liq_sig, liq_notes = self._sig_liquidation()
        vol_sigs = [
            self._sig_volume_breakout(),
            self._sig_funding(),
            self._sig_oi(),
            self._sig_orderbook(),
            self._sig_trade_flow(),
        ]
        for s in vol_sigs:
            cot.append(
                f"  {s.name}: {s.raw_value} → {s.condition} "
                f"→ score: {s.vote:+.2f} (conf {s.confidence:.2f})"
            )
        cot.append(
            f"[Liquidation] {liq_sig.raw_value} → {liq_sig.condition} "
            f"→ score: {liq_sig.vote:+.2f} (conf {liq_sig.confidence:.2f})"
        )
        for ln in liq_notes:
            cot.append(f"  {ln}")
        vol_norm = _normalize_group(vol_sigs, 5)
        cot.append(
            f"  Vol/Senti raw_sum={sum(s.vote for s in vol_sigs):.2f} "
            f"normalized={vol_norm:+.2f}/5"
        )
        check.append(
            f"[{'✅' if all(s.raw_value != 'N/A' or s.name == 'OI Change' for s in vol_sigs) else '⚠️'}] "
            f"All 5 Vol/Senti signals computed"
        )
        check.append(
            f"[{'✅' if liq_sig.raw_value != 'N/A' else '⚠️'}] "
            f"Liquidation heatmap computed (SWAP only)"
        )

        # ── Step 4: Oscillator (RSI) ──────────────────────────────────────────
        cot.append("[Oscillator] Computing RSI signals …")
        rsi4h_val = rsi(self.c4) or 50.0
        rsi1h_val = rsi(self.c1) or 50.0

        def _rsi_signal(val: float, label: str) -> SignalResult:
            if val < 20:
                return _mk(label, f"RSI={val:.1f}", "Extreme oversold",  +1, 1.00)
            elif val < 30:
                return _mk(label, f"RSI={val:.1f}", "Moderate oversold", +1, 0.75)
            elif val < 35:
                return _mk(label, f"RSI={val:.1f}", "Mild oversold",     +1, 0.50)
            elif val > 80:
                return _mk(label, f"RSI={val:.1f}", "Extreme overbought",  -1, 1.00)
            elif val > 70:
                return _mk(label, f"RSI={val:.1f}", "Moderate overbought", -1, 0.75)
            elif val > 65:
                return _mk(label, f"RSI={val:.1f}", "Mild overbought",     -1, 0.50)
            return _mk(label, f"RSI={val:.1f}", "Neutral zone", 0, 0.0)

        osc_sigs = [_rsi_signal(rsi4h_val, "RSI 4H"), _rsi_signal(rsi1h_val, "RSI 1H")]
        for s in osc_sigs:
            cot.append(f"  {s.name}: {s.raw_value} → {s.condition} → score: {s.vote:+.2f}")
        osc_norm = _normalize_group(osc_sigs, 2)
        cot.append(f"  Oscillator normalized={osc_norm:+.2f}/5")
        k4h, d4h, j4h = kdj(self.h4, self.l4, self.c4)
        cot.append(f"  KDJ(9,3,3) 4H: K={k4h} D={d4h} J={j4h} (supplementary only)")
        check.append("[✅] RSI(14) and KDJ computed")

        # ── Step 5: Weighted total ────────────────────────────────────────────
        total = (
            trend_norm * ms.w_trend
            + vol_norm  * ms.w_vol
            + osc_norm  * ms.w_osc
        ) * 2
        cot.append(
            f"[Score] Total = ({trend_norm:+.2f}×{ms.w_trend} "
            f"+ {vol_norm:+.2f}×{ms.w_vol} "
            f"+ {osc_norm:+.2f}×{ms.w_osc}) × 2 = {total:+.2f}/10"
        )
        check.append(
            f"[✅] Total Score = {total:+.2f}/10 "
            f"(weights: T={ms.w_trend} V={ms.w_vol} O={ms.w_osc})"
        )

        if total >= 6.0:
            direction, strength = "LONG",  "Strong"
        elif total >= 3.0:
            direction, strength = "LONG",  "Moderate"
        elif total <= -6.0:
            direction, strength = "SHORT", "Strong"
        elif total <= -3.0:
            direction, strength = "SHORT", "Moderate"
        else:
            direction, strength = "NEUTRAL", "—"
        cot.append(f"[Direction] {direction} ({strength})")

        # ── Step 6: Entry / SL / TP ───────────────────────────────────────────
        rr_warning: Optional[str] = None
        el = eh = em = sl = sl_pct = tp1 = tp2 = rr = 0.0
        risk_pct = pos_usdt = 0.0

        if direction != "NEUTRAL":
            el, eh, em, sl, sl_pct, tp1, tp2, rr = self._entry_sl_tp(direction, ms)
            cot.append(
                f"[EntryPlan] Entry={el:,.2f}–{eh:,.2f} Mid={em:,.2f} "
                f"SL={sl:,.2f} ({sl_pct:.2f}%) TP1={tp1:,.2f} TP2={tp2:,.2f} R:R={rr:.2f}"
            )
            if rr < 1.5:
                rr_warning = (
                    f"R:R = {rr:.2f} — Below minimum threshold (1.5). "
                    "No trade recommended."
                )
                cot.append("[EntryPlan] ⛔ R:R gate failed → direction reset to NEUTRAL")
                check.append(f"[⛔] R:R = {rr:.2f} < 1.5 → no trade")
                direction = "NEUTRAL"
            else:
                risk_pct = self._position_size(em, sl, strength, ms)
                risk_abs = abs(em - sl) / em
                pos_usdt = (
                    self.account * (risk_pct / 100) / risk_abs if risk_abs else 0.0
                )
                cot.append(
                    f"[Position] risk={risk_pct}% account={self.account:,.0f} "
                    f"→ size≈{pos_usdt:,.0f} USDT"
                )
                check.append(f"[✅] R:R = {rr:.2f} ≥ 1.5 → entry plan valid")
                check.append(
                    f"[✅] Position size = {risk_pct}% of account ≈ {pos_usdt:,.0f} USDT"
                )
        else:
            check.append("[⚪] NEUTRAL — no entry plan computed")

        # ── Step 7: Risk flags ────────────────────────────────────────────────
        risks: List[str] = []
        fr_pct = self.data.funding_rate * 100
        if abs(fr_pct) > 0.1:
            risks.append(f"Extreme funding rate ({fr_pct:.4f}%) — contrarian sentiment extreme")
        if ms.state == "High Volatility":
            risks.append("High Volatility detected — reduce position size (0.5% risk cap)")
        vol_ma20 = sma(self.v1, 20)
        if vol_ma20 and self.v1[-1] < vol_ma20 * 0.5:
            risks.append("Low volume on 1H — signal reliability reduced")
        if liq_sig.sign != 0:
            risks.append(f"Liquidation signal active: {liq_sig.condition}")
        if trend_norm > 2 and vol_norm < -2:
            risks.append(
                "Mixed Signal: Trend bullish but Vol/Senti bearish — "
                "higher risk, reduce size"
            )
        elif trend_norm < -2 and vol_norm > 2:
            risks.append(
                "Mixed Signal: Trend bearish but Vol/Senti bullish — "
                "higher risk, reduce size"
            )
        check.append(f"[{'✅' if not risks else '⚠️'}] {len(risks)} risk flag(s) identified")
        check.append(
            f"[{'✅' if all(c.confirm == '1' for c in self.data.candles_4h) else '⚠️'}] "
            "Confirmed candles only used"
        )
        check.append(f"[✅] Data timestamp: {self.data.timestamp}")

        state_label = f"{ms.state} (ADX={ms.adx:.1f}, ATR_ratio={atr_ratio:.2f}x)"
        if scalp_mode:
            state_label += " | Mode: Scalp (15m active)"
        all_sigs    = all_trend_sigs + vol_sigs + osc_sigs

        return Report(
            inst_id=self.data.inst_id,
            price=self.data.last_price,
            timestamp=self.data.timestamp,
            trend=GroupScore(
                "Trend", all_trend_sigs,
                sum(s.vote for s in all_trend_sigs), trend_norm
            ),
            volume_senti=GroupScore(
                "Volume/Senti", vol_sigs,
                sum(s.vote for s in vol_sigs), vol_norm
            ),
            oscillator=GroupScore(
                "Oscillator", osc_sigs,
                sum(s.vote for s in osc_sigs), osc_norm
            ),
            total_score=total,
            direction=direction,
            strength=strength,
            market_state=state_label,
            adx_value=ms.adx,
            entry_low=el, entry_high=eh, entry_mid=em,
            stop_loss=sl, sl_pct=sl_pct,
            tp1=tp1, tp2=tp2, rr_ratio=rr,
            position_risk_pct=risk_pct,
            position_usdt=pos_usdt,
            supplementary=self._supplementary() + liq_notes,
            evidence_bull=[s.condition for s in all_sigs if s.sign > 0 and s.confidence > 0],
            evidence_bear=[s.condition for s in all_sigs if s.sign < 0 and s.confidence > 0],
            risks=risks,
            rr_warning=rr_warning,
            cot_log=cot,
            self_check=check,
        )
