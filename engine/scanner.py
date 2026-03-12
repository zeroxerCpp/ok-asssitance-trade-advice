"""
engine/scanner.py — Multi-instrument portfolio scanner.

Depends on: models, fetcher, signals.
"""
from __future__ import annotations

from typing import List

from .models import ScanResult
from .fetcher import fetch_all
from .signals import SignalEngine


def scan_portfolio(
    inst_ids: List[str],
    account_size: float = 10_000.0,
    min_score: float = 3.0,
) -> str:
    """
    Run signal analysis on multiple instruments and return a ranked report.

    Parameters
    ----------
    inst_ids     : list of instrument IDs, e.g. ["BTC-USDT-SWAP", "SOL-USDT-SWAP"]
    account_size : total account in USDT
    min_score    : absolute score threshold used for section filtering (currently
                   all signals are shown regardless; the threshold determines the
                   "Actionable" label)

    Returns
    -------
    Formatted multi-instrument scan report as a plain-text string.
    """
    results: List[ScanResult] = []

    for inst_id in inst_ids:
        is_swap = "SWAP" in inst_id.upper()
        try:
            data   = fetch_all(inst_id, is_swap=is_swap)
            engine = SignalEngine(data, account_size=account_size, is_swap=is_swap)
            rep    = engine.run()
            results.append(ScanResult(
                inst_id=inst_id,
                price=rep.price,
                direction=rep.direction,
                strength=rep.strength,
                score=rep.total_score,
                market_state=rep.market_state,
                entry_mid=rep.entry_mid,
                stop_loss=rep.stop_loss,
                tp1=rep.tp1,
                rr_ratio=rep.rr_ratio,
                position_pct=rep.position_risk_pct,
                position_usdt=rep.position_usdt,
            ))
        except Exception as exc:
            results.append(ScanResult(
                inst_id=inst_id,
                price=0, direction="ERROR", strength="—",
                score=0, market_state="—",
                entry_mid=0, stop_loss=0, tp1=0, rr_ratio=0,
                position_pct=0, position_usdt=0,
                error=str(exc)[:80],
            ))

    # Apply min_score filter — exclude assets with |score| < min_score (neutral signals)
    results = [r for r in results if r.error or abs(r.score) >= min_score]

    # Sort: actionable first (|score| desc), then neutral, then errors
    def _sort_key(r: ScanResult):
        if r.error:
            return (2, 0.0)
        if r.direction == "NEUTRAL":
            return (1, -abs(r.score))
        return (0, -abs(r.score))

    results.sort(key=_sort_key)

    lines: List[str] = []
    lines.append("═══════════════════════════════════════════════════════")
    lines.append("📊 Portfolio Scanner Report")
    lines.append(f"   Account: {account_size:,.0f} USDT  |  Instruments: {len(inst_ids)}")
    lines.append("═══════════════════════════════════════════════════════")

    actionable = [r for r in results if r.direction not in ("NEUTRAL", "ERROR") and not r.error]
    total_alloc = sum(r.position_usdt for r in actionable)

    lines.append(f"Actionable signals : {len(actionable)} / {len(results)}")
    lines.append(
        f"Total allocated    : {total_alloc:,.0f} USDT  "
        f"({total_alloc / account_size * 100:.1f}% of account)"
    )
    lines.append("")
    lines.append("─── All Signals (ranked by |score|) ───────────────────")
    for r in results:
        lines.append(str(r))
    lines.append("")

    if actionable:
        lines.append("─── Actionable Entry Plans ────────────────────────────")
        for r in actionable:
            emoji = "🟢" if r.direction == "LONG" else "🔴"
            lines.append(
                f"  {emoji} {r.inst_id:<20} Entry≈{r.entry_mid:,.2f}  "
                f"SL={r.stop_loss:,.2f}  TP1={r.tp1:,.2f}  "
                f"R:R={r.rr_ratio:.2f}  Size≈{r.position_usdt:,.0f}USDT ({r.position_pct:.1f}%)"
            )
        lines.append("")

    lines.append("─── Capital Allocation ────────────────────────────────")
    if actionable:
        for r in actionable:
            pct_of_acc = r.position_usdt / account_size * 100
            lines.append(
                f"  {r.inst_id:<20} {r.position_usdt:>9,.0f} USDT  ({pct_of_acc:.1f}%)"
            )
        lines.append(
            f"  {'TOTAL':<20} {total_alloc:>9,.0f} USDT  "
            f"({total_alloc / account_size * 100:.1f}%)"
        )
    else:
        lines.append("  No actionable signals — hold cash.")

    lines.append("")
    lines.append("─── Caution ───────────────────────────────────────────")
    lines.append("Analysis output, not financial advice.")
    lines.append("═══════════════════════════════════════════════════════")
    return "\n".join(lines)
