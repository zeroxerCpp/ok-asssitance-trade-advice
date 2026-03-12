"""
execution/executor.py — 6-step OKX order execution chain.

Steps:
  E1: Check account balance (okx account balance)
  E2: Check existing positions (okx swap positions)
  E3: Set leverage (okx swap leverage)
  E4: Calculate contracts and place entry order (okx swap place)
  E5: Attach OCO TP/SL algo order (okx swap place-algo)
  E6: Confirm position and emit execution summary

All CLI calls are suppressed in demo mode (dry-run simulation only).
"""
from __future__ import annotations

import json
import math
import subprocess
import datetime
from typing import Optional, Union

from engine.models import Report


# ── Helpers ──────────────────────────────────────────────────────────────────

def _run(cmd: str, demo: bool) -> Union[list, dict, None]:
    """
    Execute an okx CLI command.
    In demo mode: print the command but do NOT execute it; return None.
    In live mode: execute and return parsed JSON.
    """
    if demo:
        print(f"  [DEMO] would run: {cmd}")
        return None
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"CLI error ({cmd}):\n{p.stderr.strip()}")
    return json.loads(p.stdout)


def _leverage_for(report: Report) -> int:
    """Select leverage based on signal strength and market state."""
    state = (report.market_state or "").lower()
    if "high volatility" in state:
        return 2
    if report.direction == "LONG" or report.direction == "SHORT":
        if report.total_score is not None and abs(report.total_score) >= 6:
            return 5   # Strong signal
        return 3       # Moderate signal
    return 1


# ── E1: Balance check ─────────────────────────────────────────────────────────

def _e1_check_balance(
    account_size: float,
    mode: str,
) -> float:
    """
    Check available equity. Returns effective position size in USDT.
    In demo mode returns account_size unchanged.
    """
    demo = mode == "demo"
    print("\n[E1] Checking account balance...")
    result = _run("okx account balance --json", demo=demo)
    if result is None:
        print(f"  Available equity (demo): {account_size:.2f} USDT")
        return account_size

    # Parse availEq from OKX balance response
    try:
        avail_eq = float(result[0]["details"][0]["availEq"])
    except (KeyError, IndexError, TypeError, ValueError):
        avail_eq = float(result[0].get("availEq", account_size))

    print(f"  Available equity: {avail_eq:.2f} USDT")
    if avail_eq < account_size:
        raise ValueError(
            f"⚠️ Insufficient balance. Available: {avail_eq:.2f} USDT, "
            f"requested: {account_size:.2f} USDT"
        )
    return account_size


# ── E2: Position check ────────────────────────────────────────────────────────

def _e2_check_positions(report: Report, mode: str) -> None:
    """Warn if a conflicting position already exists."""
    demo = mode == "demo"
    print("\n[E2] Checking existing positions...")
    result = _run(f"okx swap positions --instId {report.inst_id} --json", demo=demo)
    if result is None:
        print("  No open positions (demo)")
        return

    positions = result if isinstance(result, list) else [result]
    for pos in positions:
        pos_side = pos.get("posSide", "")
        sz = pos.get("sz", "0")
        avg_px = pos.get("avgPx", "?")
        direction = report.direction
        if (direction == "LONG" and pos_side == "long") or \
           (direction == "SHORT" and pos_side == "short"):
            print(
                f"  ⚠️ Existing {pos_side} position detected "
                f"(size: {sz}, entry: {avg_px}). Adding may increase risk."
            )
        elif (direction == "LONG" and pos_side == "short") or \
             (direction == "SHORT" and pos_side == "long"):
            print(
                f"  ⚠️ Opposing {pos_side} position detected. "
                f"Consider closing it before opening {direction}."
            )


# ── E3: Set leverage ──────────────────────────────────────────────────────────

def _e3_set_leverage(report: Report, lever: int, mode: str) -> None:
    """Set leverage for the instrument."""
    demo = mode == "demo"
    print(f"\n[E3] Setting leverage to {lever}x...")
    _run(
        f"okx swap leverage --instId {report.inst_id} "
        f"--lever {lever} --mgnMode cross --json",
        demo=demo,
    )
    print(f"  Leverage set: {lever}x cross margin")


# ── E4: Calculate size and place entry order ──────────────────────────────────

def _e4_place_entry(
    report: Report,
    position_size_usdt: float,
    lever: int,
    mode: str,
) -> tuple:
    """
    Calculate contract size and place the entry order.
    Returns (ordId, contracts) — ordId is None in demo mode.
    """
    demo = mode == "demo"
    print("\n[E4] Placing entry order...")

    # Fetch mark price
    mark_result = _run(
        f"okx market mark-price --instType SWAP --instId {report.inst_id} --json",
        demo=demo,
    )
    mark_price = report.price  # fallback
    if mark_result is not None:
        try:
            mark_price = float(mark_result[0]["markPx"])
        except (KeyError, IndexError, TypeError, ValueError):
            pass

    # Fetch ctVal from instruments
    ct_val = 0.001  # BTC-USDT-SWAP default fallback (0.001 BTC per contract)
    inst_result = _run(
        f"okx market instruments --instType SWAP --instId {report.inst_id} --json",
        demo=demo,
    )
    if inst_result is not None:
        try:
            ct_val = float(inst_result[0]["ctVal"])
        except (KeyError, IndexError, TypeError, ValueError):
            pass

    # contracts = floor(size_usdt * leverage / mark_price / ct_val)
    contracts = math.floor(position_size_usdt * lever / mark_price / ct_val)
    if contracts < 1:
        raise ValueError(
            f"⚠️ Position size too small. Calculated contracts: {contracts}. "
            f"Increase position size or reduce leverage."
        )

    direction = report.direction
    side = "buy" if direction == "LONG" else "sell"
    pos_side = "long" if direction == "LONG" else "short"

    # Entry price: midpoint of entry zone
    entry_price = report.entry_mid if report.entry_mid else mark_price

    print(f"  Contracts: {contracts} | Entry price: {entry_price:.4f} | Side: {side}")

    result = _run(
        f"okx swap place "
        f"--instId {report.inst_id} "
        f"--side {side} "
        f"--ordType limit "
        f"--px {entry_price:.4f} "
        f"--sz {contracts} "
        f"--posSide {pos_side} "
        f"--tdMode cross --json",
        demo=demo,
    )

    ord_id = None
    if result is not None:
        try:
            ord_id = result[0].get("ordId")
            print(f"  Entry order placed: ordId={ord_id}")
        except (KeyError, IndexError, TypeError):
            pass
    return ord_id, contracts


# ── E5: Attach OCO TP/SL ──────────────────────────────────────────────────────

def _e5_place_oco(
    report: Report,
    contracts: int,
    mode: str,
) -> Optional[str]:
    """Place OCO take-profit / stop-loss algo order. Returns algoId."""
    demo = mode == "demo"
    print("\n[E5] Attaching OCO TP/SL...")

    direction = report.direction
    side = "sell" if direction == "LONG" else "buy"
    pos_side = "long" if direction == "LONG" else "short"

    tp = report.tp1
    sl = report.stop_loss

    if tp is None or sl is None:
        print("  ⚠️ TP/SL not available in report — skipping OCO order")
        return None

    print(f"  TP1={tp:.4f} | SL={sl:.4f}")

    result = _run(
        f"okx swap place-algo "
        f"--instId {report.inst_id} "
        f"--tdMode cross "
        f"--side {side} "
        f"--posSide {pos_side} "
        f"--sz {contracts} "
        f"--ordType oco "
        f"--tpTriggerPx {tp:.4f} "
        f"--tpOrdPx -1 "
        f"--slTriggerPx {sl:.4f} "
        f"--slOrdPx -1 --json",
        demo=demo,
    )

    algo_id = None
    if result is not None:
        try:
            algo_id = result[0].get("algoId")
            print(f"  OCO algo order placed: algoId={algo_id}")
        except (KeyError, IndexError, TypeError):
            pass
    return algo_id


# ── E6: Execution summary ─────────────────────────────────────────────────────

def _e6_summary(
    report: Report,
    lever: int,
    ord_id: Optional[str],
    algo_id: Optional[str],
    mode: str,
) -> None:
    """Print structured execution confirmation."""
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    direction_emoji = "🟢" if report.direction == "LONG" else "🔴"
    mode_label = "DEMO" if mode == "demo" else "LIVE"
    tp1 = report.tp1
    sl = report.stop_loss
    rr = report.rr_ratio

    print(f"""
═══════════════════════════════════════════
{"✅" if mode == "live" else "🔵"} OK Trading Advisor — Execution {mode_label}
═══════════════════════════════════════════
📈 Instrument  : {report.inst_id}
📊 Direction   : {direction_emoji} {report.direction}
💰 Entry Price : ~{report.price:.4f} USDT
⚙️  Leverage    : {lever}x cross
🛑 Stop-Loss   : {f"{sl:.4f}" if sl else "N/A"} USDT
🎯 Take-Profit : {f"{tp1:.4f}" if tp1 else "N/A"} USDT{f" (R:R = {rr:.1f})" if rr else ""}
📦 Order ID    : {ord_id or "(demo — not placed)"}
🔒 Algo ID     : {algo_id or "(demo — not placed)"}
🕒 Time        : {ts}
═══════════════════════════════════════════""")


# ── Public API ────────────────────────────────────────────────────────────────

def execute_signal(
    report: Report,
    account_size: float = 10_000.0,
    mode: str = "demo",
) -> None:
    """
    Execute a trade signal produced by SignalEngine.run().

    Parameters
    ----------
    report       : Report object from SignalEngine.run()
    account_size : Total account size in USDT (used for position sizing)
    mode         : "demo" (dry-run, no real orders) or "live" (real orders)

    Raises
    ------
    ValueError   : If balance is insufficient or position size is too small
    RuntimeError : If CLI command fails (live mode only)
    """
    if report.direction == "NEUTRAL":
        print("⚪ Signal is NEUTRAL — no trade executed.")
        return

    if mode not in ("demo", "live"):
        raise ValueError(f"mode must be 'demo' or 'live', got {mode!r}")

    print(f"\n{'='*45}")
    print(f"🚀 OK Trading Advisor — Execution Chain [{mode.upper()}]")
    print(f"{'='*45}")
    print(f"Signal: {report.direction} | Score: {report.total_score:.2f} | "
          f"Strength: {report.strength}"
          if report.total_score is not None
          else f"Signal: {report.direction} | Score: N/A | Strength: {report.strength}")

    # Staleness check
    print(f"\n⚠️  Signal timestamp: {report.timestamp}")
    print("   If > 5 minutes have passed, re-run analysis before proceeding.\n")

    lever = _leverage_for(report)

    # Position size from report or fallback
    pos_size_usdt = report.position_usdt
    if pos_size_usdt is None or pos_size_usdt <= 0:
        risk_pct = 0.02 if (report.strength or "").lower() == "strong" else 0.01
        pos_size_usdt = account_size * risk_pct
    pos_size_usdt = min(pos_size_usdt, account_size * 0.10)  # hard cap at 10%

    # E1–E6
    effective_size = _e1_check_balance(account_size, mode)
    _e2_check_positions(report, mode)
    _e3_set_leverage(report, lever, mode)
    ord_id, contracts = _e4_place_entry(report, pos_size_usdt, lever, mode)
    algo_id = _e5_place_oco(report, contracts, mode)
    _e6_summary(report, lever, ord_id, algo_id, mode)
