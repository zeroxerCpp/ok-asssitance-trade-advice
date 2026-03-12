# execution/ — OKX Order Execution Layer

Connects the `SignalEngine` output to the `okx-trade-cli` / `okx-trade-mcp` execution chain to place real or simulated orders on OKX.

---

## Purpose

The `execution/` module bridges the gap between signal generation and order placement. It reads a `Report` produced by `engine.SignalEngine` and executes a 6-step order chain (E1–E6) using the `okx` CLI.

---

## Modes

| Mode | Description |
|---|---|
| `demo` | Dry-run — prints all CLI commands but does **not** execute them. Safe for testing. |
| `live` | Real orders — executes CLI commands against the OKX API. Requires valid credentials. |

---

## Prerequisites

Valid OKX API credentials must be set as environment variables before using live mode:

```bash
export OKX_API_KEY="your-api-key"
export OKX_SECRET_KEY="your-secret-key"
export OKX_PASSPHRASE="your-passphrase"
```

The `okx` CLI must also be installed:

```bash
npm install -g @okx_ai/okx-trade-cli
```

---

## Quick Usage

```python
from engine import fetch_all, SignalEngine
from execution import execute_signal

data   = fetch_all("BTC-USDT-SWAP")
report = SignalEngine(data, account_size=10_000).run()
print(report.text)

# Demo mode (safe, no real orders)
execute_signal(report, account_size=10_000, mode="demo")

# Live mode (real orders — requires API credentials)
# execute_signal(report, account_size=10_000, mode="live")
```

---

## 6-Step Execution Chain

| Step | CLI Command | Description |
|---|---|---|
| E1 | `okx account balance` | Check available equity; validate against requested position size |
| E2 | `okx swap positions` | Detect conflicting or opposing open positions |
| E3 | `okx swap leverage` | Set leverage (2–5×) based on signal strength and market state |
| E4 | `okx swap place` | Calculate contract count and place limit entry order |
| E5 | `okx swap place-algo` | Attach OCO take-profit / stop-loss algo order |
| E6 | _(summary)_ | Print structured execution confirmation with all order IDs |

---

## Error Codes

| Code | Meaning | Action |
|---|---|---|
| 51020 | Order quantity invalid | Recalculate `sz` using `minSz` from instruments endpoint |
| 51008 | Insufficient margin | Reduce `position_size_usdt` by 50% and retry |
| 51131 | Leverage not modified | Ignore — already at target leverage |
| 58350 | Algo order failed | Fall back to SL-only order |
