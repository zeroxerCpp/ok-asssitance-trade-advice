"""
engine/models.py — All shared data-structures (dataclasses).
No business logic here; import-safe from any other module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Raw market data
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Candle:
    ts:      int
    open:    float
    high:    float
    low:     float
    close:   float
    vol:     float
    confirm: str   # "1" = confirmed, "0" = forming


@dataclass
class MarketData:
    inst_id:       str
    candles_1d:    List[Candle]
    candles_4h:    List[Candle]
    candles_1h:    List[Candle]
    last_price:    float
    funding_rate:  float                        # raw value, e.g. 0.00375
    open_interest: float                        # latest OI in contracts
    oi_history:    List[float]                  # last N OI snapshots for MA5
    liquidations:  List[dict]                   # raw liquidation-order dicts
    bids_top10:    List[Tuple[float, float]]    # (price, size)
    asks_top10:    List[Tuple[float, float]]
    trades:        List[dict]                   # raw trade dicts
    timestamp:     str                          # UTC ISO string
    candles_15m:   List[Candle] = field(default_factory=list)  # optional 15m candles for scalp mode


# ─────────────────────────────────────────────────────────────────────────────
# Signal scoring
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SignalResult:
    name:       str
    raw_value:  str
    condition:  str
    sign:       int     # +1 / -1 / 0
    confidence: float   # 0.0 – 1.0
    vote:       float   # sign × confidence

    def __str__(self) -> str:
        sign_str = f"+{self.vote:.2f}" if self.vote >= 0 else f"{self.vote:.2f}"
        return (f"  {self.name}: {self.raw_value} → {self.condition} "
                f"→ score: {sign_str} (confidence: {self.confidence:.2f})")


@dataclass
class GroupScore:
    name:       str
    signals:    List[SignalResult]
    raw_sum:    float   # Σ(sign × confidence)
    normalized: float   # mapped to [−5, +5]


# ─────────────────────────────────────────────────────────────────────────────
# Market state
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MarketState:
    state:    str     # "Trending" | "Ranging" | "High Volatility" | "Low Liquidity" | "Normal"
    adx:      float
    atr14:    float
    atr_ma10: float
    vol_ratio: float
    w_trend:  float
    w_vol:    float
    w_osc:    float


# ─────────────────────────────────────────────────────────────────────────────
# Final report
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Report:
    inst_id:           str
    price:             float
    timestamp:         str
    trend:             GroupScore
    volume_senti:      GroupScore
    oscillator:        GroupScore
    total_score:       float
    direction:         str      # LONG / SHORT / NEUTRAL
    strength:          str      # Strong / Moderate / —
    market_state:      str
    adx_value:         float
    entry_low:         float
    entry_high:        float
    entry_mid:         float
    stop_loss:         float
    sl_pct:            float
    tp1:               float
    tp2:               float
    rr_ratio:          float
    position_risk_pct: float
    position_usdt:     float    # estimated USDT position size
    supplementary:     List[str]
    evidence_bull:     List[str]
    evidence_bear:     List[str]
    risks:             List[str]
    rr_warning:        Optional[str]
    cot_log:           List[str]   # Chain-of-Thought steps
    self_check:        List[str]   # Self-verification checklist

    def as_dict(self) -> dict:
        return {
            "inst_id":       self.inst_id,
            "price":         self.price,
            "timestamp":     self.timestamp,
            "trend_score":   self.trend.normalized,
            "volume_score":  self.volume_senti.normalized,
            "osc_score":     self.oscillator.normalized,
            "total_score":   self.total_score,
            "direction":     self.direction,
            "strength":      self.strength,
            "market_state":  self.market_state,
            "adx":           self.adx_value,
            "entry_zone":    [self.entry_low, self.entry_high],
            "stop_loss":     self.stop_loss,
            "tp1":           self.tp1,
            "tp2":           self.tp2,
            "rr_ratio":      self.rr_ratio,
            "position_usdt": self.position_usdt,
        }

    @property
    def text(self) -> str:
        lines = []
        lines.append("═══════════════════════════════════════════")
        lines.append("📊 OK Trading Advisor — Signal Report")
        lines.append("═══════════════════════════════════════════")
        lines.append(f"🕒 Time        : {self.timestamp}")
        lines.append(f"📈 Instrument  : {self.inst_id}")
        lines.append(f"💰 Price       : {self.price:,.2f} USDT")
        lines.append("")
        lines.append("─── Step-by-Step Computation (CoT) ────────")
        for step in self.cot_log:
            lines.append(f"  {step}")
        lines.append("")
        lines.append("─── Self-Verification Checklist ────────────")
        for item in self.self_check:
            lines.append(f"  {item}")
        lines.append("")
        lines.append("─── Indicator Detail ──────────────────────")
        for s in self.trend.signals + self.volume_senti.signals + self.oscillator.signals:
            lines.append(str(s))
        lines.append("")
        lines.append("─── Supplementary (RSI / KDJ) ─────────────")
        for n in self.supplementary:
            lines.append(f"  {n}")
        lines.append("")
        lines.append("─── Scores ────────────────────────────────")
        lines.append(f"Trend          : {self.trend.normalized:+.2f}/5  ({len(self.trend.signals)} signals)")
        lines.append(f"Oscillator     : {self.oscillator.normalized:+.2f}/5")
        lines.append(f"Volume/Senti   : {self.volume_senti.normalized:+.2f}/5  ({len(self.volume_senti.signals)} signals)")
        lines.append("─────────────────────────────────────────")
        lines.append(f"Total Score    : {self.total_score:+.2f}/10")
        lines.append(f"Market State   : {self.market_state} (ADX = {self.adx_value:.1f})")
        lines.append("")
        lines.append("─── Recommendation ────────────────────────")
        emoji = {"LONG": "🟢", "SHORT": "🔴", "NEUTRAL": "⚪"}.get(self.direction, "⚪")
        lines.append(f"Direction  : {emoji} {self.direction}")
        lines.append(f"Strength   : {self.strength}")
        lines.append("")
        if self.rr_warning:
            lines.append(f"⚠️  {self.rr_warning}")
        else:
            lines.append("─── Entry Plan ────────────────────────────")
            lines.append(f"Entry Zone : {self.entry_low:,.2f} – {self.entry_high:,.2f}")
            lines.append(f"Entry Mid  : {self.entry_mid:,.2f}")
            lines.append(f"Stop-Loss  : {self.stop_loss:,.2f}  ({self.sl_pct:.2f}% from entry)")
            lines.append(f"TP1        : {self.tp1:,.2f}  (R:R = 1.5)")
            lines.append(f"TP2        : {self.tp2:,.2f}  (R:R = 3.0)")
            lines.append(f"R:R        : {self.rr_ratio:.2f}")
            lines.append(f"Position   : {self.position_risk_pct:.1f}% of account  ≈ {self.position_usdt:,.0f} USDT")
        lines.append("")
        lines.append("─── Key Evidence ──────────────────────────")
        for b in self.evidence_bull:
            lines.append(f"✅ {b}")
        for r in self.risks:
            lines.append(f"⚠️  {r}")
        for b in self.evidence_bear:
            lines.append(f"❌ {b}")
        lines.append("")
        lines.append("─── Caution ───────────────────────────────")
        lines.append("Analysis output, not financial advice.")
        lines.append("Always confirm with your own judgment.")
        lines.append("═══════════════════════════════════════════")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio scanner result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScanResult:
    inst_id:       str
    price:         float
    direction:     str
    strength:      str
    score:         float
    market_state:  str
    entry_mid:     float
    stop_loss:     float
    tp1:           float
    rr_ratio:      float
    position_pct:  float
    position_usdt: float
    error:         Optional[str] = None

    def __str__(self) -> str:
        if self.error:
            return f"  {self.inst_id:<20} ERROR: {self.error}"
        emoji = {"LONG": "🟢", "SHORT": "🔴", "NEUTRAL": "⚪"}.get(self.direction, "⚪")
        return (
            f"  {self.inst_id:<20} {emoji} {self.direction:<8} {self.strength:<10} "
            f"score={self.score:+.1f}  state={self.market_state.split('(')[0].strip():<18} "
            f"size≈{self.position_usdt:,.0f}USDT"
        )
