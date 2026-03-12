"""
engine/fetcher.py — OKX CLI data-fetching layer.

Depends only on stdlib + engine.models.
"""
from __future__ import annotations

import json
import datetime
import subprocess
from typing import List

from .models import Candle, MarketData


def _run_cmd(cmd: str) -> list | dict:
    """Execute an `okx` CLI command and return parsed JSON."""
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"CLI error: {cmd}\n{p.stderr}")
    return json.loads(p.stdout)


def _parse_candles(raw: list) -> List[Candle]:
    """Convert raw CLI candle rows to sorted, confirmed-only Candle objects."""
    rows = []
    for r in raw:
        confirm = r[8] if len(r) > 8 else "1"
        rows.append(Candle(
            ts=int(r[0]),
            open=float(r[1]),
            high=float(r[2]),
            low=float(r[3]),
            close=float(r[4]),
            vol=float(r[5]),
            confirm=str(confirm),
        ))
    rows.sort(key=lambda x: x.ts)
    return [c for c in rows if c.confirm == "1"]   # confirmed candles only


def fetch_all(inst_id: str, is_swap: bool = True) -> MarketData:
    """
    Pull all required market data from OKX CLI.

    Parameters
    ----------
    inst_id  : e.g. "BTC-USDT-SWAP"
    is_swap  : True for perpetual swaps; False for spot

    Returns
    -------
    MarketData with candles (1D/4H/1H), ticker, funding, OI, liquidations,
    orderbook and trades populated.
    """
    inst_type = "SWAP" if is_swap else "SPOT"

    c1d = _parse_candles(_run_cmd(f"okx market candles {inst_id} --bar 1D --limit 100 --json"))
    c4h = _parse_candles(_run_cmd(f"okx market candles {inst_id} --bar 4H --limit 200 --json"))
    c1h = _parse_candles(_run_cmd(f"okx market candles {inst_id} --bar 1H --limit 200 --json"))

    tick = _run_cmd(f"okx market ticker {inst_id} --json")[0]
    fund = _run_cmd(f"okx market funding-rate {inst_id} --json")[0] if is_swap else {}
    oi_r = (
        _run_cmd(
            f"okx market open-interest --instType {inst_type} --instId {inst_id} --json"
        )[0]
        if is_swap
        else {}
    )
    ob  = _run_cmd(f"okx market orderbook {inst_id} --sz 20 --json")[0]
    trd = _run_cmd(f"okx market trades {inst_id} --limit 50 --json")

    # ── OI history for MA5 (best-effort; CLI only gives a single snapshot) ──
    oi_val = float(oi_r.get("oi", 0)) if oi_r else 0.0
    try:
        oi_hist_raw = _run_cmd(
            f"okx market open-interest --instType {inst_type} --instId {inst_id} --json"
        )
        oi_history = [
            float(x.get("oi", oi_val))
            for x in (oi_hist_raw if isinstance(oi_hist_raw, list) else [oi_hist_raw])
        ]
        if len(oi_history) < 5:
            oi_history = [oi_val] * 5
    except Exception:
        oi_history = [oi_val] * 5

    # ── Liquidation heatmap (SWAP only; graceful fallback to []) ──────────
    liquidations: List[dict] = []
    if is_swap:
        try:
            liq_raw = _run_cmd(
                f"okx market liquidation-orders --instType {inst_type} "
                f"--instId {inst_id} --state filled --limit 100 --json"
            )
            if isinstance(liq_raw, list):
                liquidations = liq_raw
        except Exception:
            pass

    bids = [(float(b[0]), float(b[1])) for b in ob.get("bids", [])[:10]]
    asks = [(float(a[0]), float(a[1])) for a in ob.get("asks", [])[:10]]

    return MarketData(
        inst_id=inst_id,
        candles_1d=c1d,
        candles_4h=c4h,
        candles_1h=c1h,
        last_price=float(tick.get("last", 0)),
        funding_rate=float(fund.get("fundingRate", 0)) if fund else 0.0,
        open_interest=oi_val,
        oi_history=oi_history,
        liquidations=liquidations,
        bids_top10=bids,
        asks_top10=asks,
        trades=trd,
        timestamp=datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
    )
