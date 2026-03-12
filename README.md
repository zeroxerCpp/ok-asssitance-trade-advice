# ok-assistance-trade-advice

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Overview

`ok-assistance-trade-advice` is a multi-timeframe OKX perpetual/spot signal engine that
analyses market data across 1D, 4H, and 1H candle intervals.  It uses
`okx-trade-cli` for read-only data collection (no API credentials required) and
outputs a structured trade recommendation complete with entry zone, take-profit
targets, stop-loss level, and a risk-adjusted position size.

## Architecture

```
signal_engine.py  (CLI entry point)
       │
       └── engine/
           ├── __init__.py        (public API)
           ├── models.py          (dataclasses: Candle, MarketData, Report, …)
           ├── indicators.py      (pure functions: EMA, MACD, RSI, BB, KDJ, ATR, SuperTrend, Ichimoku, ADX)
           ├── market_state.py    (ADX/ATR/Volume → MarketState + dynamic weights)
           ├── fetcher.py         (OKX CLI → MarketData)
           ├── signals.py         (SignalEngine: scoring, entry/SL/TP, report)
           └── scanner.py         (multi-instrument portfolio scanner)
```

## Prerequisites

```bash
npm install -g @okx_ai/okx-trade-cli   # OKX CLI (data collection, no credentials needed)
python3 -m pip install --upgrade pip    # Python 3.9+
```

No third-party Python packages are required (stdlib only).

## Quickstart

### CLI

```bash
# Analyze BTC perpetual swap with 10,000 USDT account
python3 signal_engine.py BTC-USDT-SWAP 10000

# Analyze ETH spot
python3 signal_engine.py ETH-USDT 5000
```

### Python API

```python
from engine import fetch_all, SignalEngine

data   = fetch_all("BTC-USDT-SWAP")
report = SignalEngine(data, account_size=10_000).run()
print(report.text)
print(report.as_dict())  # machine-readable
```

### Portfolio scanner

```python
from engine import scan_portfolio

print(scan_portfolio(["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"], account_size=10_000))
```

## Signal Engine Summary

| Group | Signals | Scoring |
|---|---|---|
| Trend (1D + 4H) | EMA cross, MACD, SuperTrend, Bollinger Band, Ichimoku | sign × confidence → normalized [−5, +5] |
| Volume & Sentiment (4H + 1H) | Volume breakout, Funding rate, OI change, Order book, Trade flow | sign × confidence → normalized [−5, +5] |
| Oscillator | RSI(14) 4H + 1H | sign × confidence → normalized [−5, +5] |
| Market State | ADX(14), ATR expansion, Volume ratio | Selects dynamic weights (Trending / Ranging / High Volatility / Low Liquidity / Normal) |
| Liquidation Heatmap | `liquidation-orders` (SWAP only) | Supplementary evidence only — not scored |

Final score: `(Trend × w_trend + Volume × w_vol + Oscillator × w_osc) × 2` → range [−10, +10]

## Running Tests

```bash
python3 -m pytest tests/ -v
```

## Skill File

`signal_skill.md` is the agent skill definition used by GitHub Copilot / AI agents.
See `signal_skill.md` for the full protocol, including the mandatory chain-of-thought
computation rules and self-verification checklist.

## License

MIT
