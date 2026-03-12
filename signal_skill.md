---
name: ok-trading-advisor
description: >
  Multi-timeframe market analysis and trade recommendation engine.
  Use when user asks for: 'trading advice', 'should I buy BTC', 'analyze BTC market',
  'is it a good time to long/short', 'technical analysis', 'signal analysis', 'entry point',
  'suggest TP/SL', 'signal engine', 'trend analysis', 'RSI signal', 'MACD signal',
  'EMA crossover', 'Bollinger Band signal', 'volume analysis', 'market analysis',
  or any request to assess market conditions and produce a trade recommendation.
  Collects multi-timeframe market data via okx-trade-cli, computes trend/oscillator/volume
  signals, and outputs a structured directional recommendation with entry zone, TP, and SL.
  Data collection is read-only (no credentials needed); order execution requires okx-cex-trade.
license: MIT
author: ok-assistance
version: 1.0.0
agent:
  requires:
    bins: ["okx"]
  install:
    - id: npm
      kind: node
      package: "@okx_ai/okx-trade-cli"
      bins: ["okx"]
---

# OK Trading Advisor

Multi-timeframe market analysis and trade recommendation engine.

Collects real-time market data via `okx-trade-cli`, computes trend/oscillator/volume
signals using the OK-Assistance signal engine, and returns a structured directional
recommendation with entry zone, take-profit, and stop-loss.

**Note:** Data collection is read-only and requires no API credentials. Order execution
requires `okx-cex-trade` and valid API credentials.

---

## Prerequisites

- Install `okx` CLI:
  ```bash
  npm install -g @okx_ai/okx-trade-cli
  ```
- Verify install:
  ```bash
  okx market ticker BTC-USDT
  ```

---

## Quickstart

Collect market data and compute signals:

```bash
# Multi-timeframe candles
okx market candles BTC-USDT-SWAP --bar 1D --limit 60 --json
okx market candles BTC-USDT-SWAP --bar 4H --limit 60 --json
okx market candles BTC-USDT-SWAP --bar 1H --limit 60 --json

# Market context
okx market ticker BTC-USDT-SWAP --json
okx market funding-rate BTC-USDT-SWAP --json
okx market open-interest --instType SWAP --instId BTC-USDT-SWAP --json
okx market orderbook BTC-USDT-SWAP --sz 20 --json
okx market trades BTC-USDT-SWAP --limit 50 --json
```

---

## Commands

All commands are READ-only market data queries.

| # | Command | Description |
|---:|:---|:---|
| 1 | `okx market candles <instId> --bar 1D --limit 60` | Daily OHLCV (trend bias, BBands, MACD) |
| 2 | `okx market candles <instId> --bar 4H --limit 60` | 4H OHLCV (entry timing, EMA, RSI) |
| 3 | `okx market candles <instId> --bar 1H --limit 60` | 1H OHLCV (entry confirmation, volume) |
| 4 | `okx market candles <instId> --bar 15m --limit 60` | 15m OHLCV (intraday entry precision) |
| 5 | `okx market ticker <instId>` | Latest price, 24h high/low/vol |
| 6 | `okx market funding-rate <instId>` | Current + next funding rate (sentiment) |
| 7 | `okx market funding-rate <instId> --history --limit 20` | Historical funding rate trend |
| 8 | `okx market open-interest --instType SWAP --instId <id>` | OI (position conviction) |
| 9 | `okx market orderbook <instId> --sz 20` | Bid/ask depth (liquidity) |
| 10 | `okx market trades <instId> --limit 50` | Recent trades (buy/sell pressure) |
| 11 | `okx market mark-price --instType SWAP --instId <id>` | Mark price vs last (divergence) |
| 12 | `okx market index-ticker --instId BTC-USD` | Index price (spot reference) |

---

## Signal Engine

### Trend Signals (1D + 4H)

| Signal | Indicator | Bullish | Bearish |
|:---|:---|:---|:---|
| EMA Crossover | EMA(9) / EMA(21) | EMA9 > EMA21, crossed up | EMA9 < EMA21, crossed down |
| MACD | MACD(12,26,9) | MACD > signal, histogram expanding | MACD < signal, histogram expanding |
| SuperTrend | ATR(10) × 3 | Price > SuperTrend band | Price < SuperTrend band |
| Bollinger Band | BB(20,2) | Price bounced from lower band | Price rejected upper band |
| Ichimoku | (9,26,52) | Price > cloud, TK cross bullish | Price < cloud, TK cross bearish |

Scoring: +1 (bullish), −1 (bearish), 0 (neutral).  
**Trend Score** = sum of 5 votes. Range: −5 to +5.

### Volume & Sentiment Signals (4H + 1H)

| Signal | Source | Bullish | Bearish |
|:---|:---|:---|:---|
| Volume Breakout | 1H volume vs MA(20) | Vol > 2× MA with up candle | Vol > 2× MA with down candle |
| Funding Rate | `market funding-rate` | Funding < −0.01% (contrarian long) | Funding > +0.05% (contrarian short) |
| OI Change | `market open-interest` | OI rising + price rising | OI rising + price falling |
| Order Book | `market orderbook` | Bid depth > ask depth | Ask depth > bid depth |
| Trade Flow | `market trades` | Majority buy-side | Majority sell-side |

Scoring: +1 (bullish), −1 (bearish), 0 (neutral).  
**Volume/Senti Score** = sum of 5 votes. Range: −5 to +5.

### Final Score & Recommendation

**Total Score** = (Trend × 0.4 + Volume/Senti × 0.60) × 2 (normalized to −10..+10)

| Score Range | Direction | Action |
|---:|:---:|:---|
| +6.0 to +10 | 🟢 LONG | Strong buy |
| +3.0 to +5.9 | 🟡 LONG | Moderate buy |
| −2.9 to +2.9 | ⚪ NEUTRAL | No trade |
| −5.9 to −3.0 | 🟡 SHORT | Moderate sell |
| −10 to −5.9 | 🔴 SHORT | Strong sell |

## Workflow

### Step 1: Identify instrument and timeframe

- **Default**: SWAP (perpetual), e.g. `BTC-USDT-SWAP`
- **Spot**: use `BTC-USDT` if user specifies "spot"
- **Timeframes**: 1D (trend) + 4H (signal) + 1H (entry) by default
- **Scalp/intraday**: add 15m, reduce 1D weight
- **Swing/position**: focus on 1D + 4H, skip 15m

### Step 2: Collect market data

```bash
okx market candles <instId> --bar 1D --limit 60 --json
okx market candles <instId> --bar 4H --limit 60 --json
okx market candles <instId> --bar 1H --limit 60 --json
okx market ticker <instId> --json
okx market funding-rate <instId> --json
okx market funding-rate <instId> --history --limit 20 --json
okx market open-interest --instType SWAP --instId <id> --json
okx market orderbook <instId> --sz 20 --json
okx market trades <instId> --limit 50 --json
```

### Step 3: Compute signals

For each timeframe, calculate:

1. **EMA(9) and EMA(21)** — check crossover on last 3 candles
2. **MACD(12,26,9)** — check direction and histogram
3. **Bollinger Bands(20,2)** — check price position and squeeze
4. **RSI(14)** — detect oversold/overbought
5. **KDJ(9,3,3)** — check K/D crosses
6. **Volume MA(20)** — compare latest vs average
7. **Funding Rate** — assess magnitude
8. **OI trend** — compare latest vs 5-period average
9. **Order Book** — sum top-10 bid vs ask depth
10. **Trade Flow** — count buy vs sell among last 50 trades

Score each signal per the tables above. Compute weighted total.

> **Note:** RSI(14) and KDJ(9,3,3) are supplementary confirmation signals. They are **not** included in the primary score calculation. Use them as ✅ or ⚠️ evidence in the Key Evidence section of the report only.

### Step 4: Generate report

Output structured recommendation:

```
═══════════════════════════════════════════
📊 OK Trading Advisor — Signal Report
═══════════════════════════════════════════
🕒 Time        : <timestamp>
📈 Instrument  : <instId>
💰 Price       : <last> USDT

─── Scores ────────────────────────────────
Trend          : <score>/5  (<signals>)
Oscillator     : <score>/5  (<signals>)
Volume/Senti   : <score>/5  (<signals>)
─────────────────────────────────────────
Total Score    : <score>/10

─── Recommendation ────────────────────────
Direction  : 🟢 LONG / 🔴 SHORT / ⚪ NEUTRAL
Strength   : Strong / Moderate
Timeframe  : <holding period>

─── Entry Plan ────────────────────────────
Entry Zone : <price range>
Stop-Loss  : <price>  (<% from entry>)
Take-Profit: <price>  (<% from entry>, R:R = <ratio>)
Position   : <% of account>

─── Key Evidence ──────────────────────────
✅ <bullish signal 1>
✅ <bullish signal 2>
⚠️  <risk factor>
❌ <bearish signal if any>

─── Caution ───────────────────────────────
Analysis output, not financial advice.
Always confirm with your own judgment.
═══════════════════════════════════════════
```

### Step 5: Offer execution

Ask:

> ⚠️ Signal generated at `<timestamp>`. Market conditions may have changed.
> If more than **5 minutes** have passed since data collection, re-run analysis before executing.
>
> Trade this signal? Reply: `yes demo|live <USDT amount> [max <X>% of account]`
>
> Recommended position size: ≤ 2% of account per trade unless signal strength is **Strong**.

---

## Examples

**"Analyze BTC"**

```
→ Collect 1D + 4H + 1H candles for BTC-USDT-SWAP
→ Collect ticker, funding-rate, OI, orderbook, trades
→ Compute signals and output report
```

**"Should I short ETH?"**

```
→ Collect ETH-USDT-SWAP data
→ If score ≤ −3: "Short signal confirmed. Entry: X, TP: Y, SL: Z"
→ Else: "Signal does not support short. Score: X (direction)"
```

**"Quick scan: BTC or ETH, which one?"**

```
→ Collect 4H + 1H for BTC and ETH
→ BTC score: +5.2 (Moderate Long)
→ ETH score: +7.1 (Strong Long)
→ "Trade ETH. Entry: X, TP: Y, SL: Z"
```

## Edge Cases

- **Neutral score (−2.9 to +2.9)**: do NOT trade. "Signal is neutral (X). Wait for confirmation."
- **Contradictory signals** (e.g., Trend +4, Oscillator −3): flag "Mixed Signal — higher risk", reduce position size.
- **Extreme funding** (< −0.1% or > +0.1%): flag as sentiment extreme, use contrarian logic.
- **OI spike + price drop**: bearish divergence — upgrade short strength by +1.
- **Low volume** (< 0.5× MA20): flag "Low Volume — signal reliability reduced", avoid entry.
- **Spot instruments**: skip funding-rate and OI; use Trend + Oscillator + Volume only.
- **Insufficient candles** (< 26): note "Insufficient history for MACD", skip that signal.
- **Price at extremes**: run `okx market price-limit <instId>` before recommending near limits.

---

## Indicators & Formulas

- **EMA(n)**: `EMAᵢ = closeᵢ × k + EMAᵢ₋₁ × (1−k)`, where `k = 2/(n+1)`
- **MACD**: `MACD = EMA(12) − EMA(26)`, `Signal = EMA(9) of MACD`
- **BB(20,2)**: `Mid = SMA(20)`, `Upper/Lower = Mid ± 2σ`
- **RSI(14)**: `RS = AvgGain/AvgLoss`, `RSI = 100 − 100/(1+RS)`
- **KDJ**: `%K = (Close − Low₉)/(High₉ − Low₉) × 100`, `%D = SMA(%K)`, `J = 3K − 2D`

- **ATR(n)**: True Range `TRᵢ = max(Highᵢ − Lowᵢ, |Highᵢ − Closeᵢ₋₁|, |Lowᵢ − Closeᵢ₋₁|)`, then `ATR = EMA(TR, n)`
- **SuperTrend(10, 3)**: `BasicUpper = (High+Low)/2 + 3×ATR(10)`, `BasicLower = (High+Low)/2 − 3×ATR(10)`. Price above final lower band → bullish; price below final upper band → bearish.

Candle columns: `[ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]`

⚠️ Only use candles where confirm == "1". The last (most recent) candle may still be forming and should be excluded from all indicator calculations.

---

## Notes

- All data commands are public, no credentials required.
- `--json` returns raw OKX API v5 data for precise computation.
- Skill does not store state — always collect fresh data.
- Rate limit: 20 requests per 2 seconds per IP.
- Do not provide code unless specifically requested by the user.
