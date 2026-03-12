# OK-TradeKit-signal-middleware


![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Overview

`OK-TradeKit-signal-middleware` is a multi-timeframe OKX perpetual/spot signal engine that
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


# 基于OK Trade kit的信号引擎中间件（中文翻译）

## 概述

`OK-TradeKit-signal-middleware` 是一个多时间周期的 OKX 永续/现货信号引擎，基于主流信号策略，分析 1D、4H 和 1H 的蜡烛图数据。它使用 `okx-trade-cli` 进行只读数据采集（无需 API 凭证），并输出结构化的交易建议，包含入场区间、止盈目标、止损位置以及基于风险的仓位大小建议。

## 架构

```
signal_engine.py  （CLI 入口）
       │
       └── engine/
           ├── __init__.py        （公共 API）
           ├── models.py          （数据类：Candle、MarketData、Report 等）
           ├── indicators.py      （纯函数：EMA、MACD、RSI、BB、KDJ、ATR、SuperTrend、Ichimoku、ADX）
           ├── market_state.py    （根据 ADX/ATR/成交量判断 MarketState 并动态加权）
           ├── fetcher.py         （OKX CLI → MarketData）
           ├── signals.py         （SignalEngine：评分、入场/止损/止盈、报告）
           └── scanner.py         （多标的组合扫描器）
```

## 先决条件

```bash
npm install -g @okx_ai/okx-trade-cli   # OKX CLI（仅用于数据采集，无需凭证）
python3 -m pip install --upgrade pip    # 需要 Python 3.9+
```

本项目不依赖第三方 Python 包（仅使用标准库）。

## 快速开始

### CLI

```bash
# 使用 10,000 USDT 账户分析 BTC 永续合约
python3 signal_engine.py BTC-USDT-SWAP 10000

# 分析 ETH 现货
python3 signal_engine.py ETH-USDT 5000
```

### Python API

```python
from engine import fetch_all, SignalEngine

data   = fetch_all("BTC-USDT-SWAP")
report = SignalEngine(data, account_size=10_000).run()
print(report.text)
print(report.as_dict())  # 机器可读输出
```

### 组合扫描器

```python
from engine import scan_portfolio

print(scan_portfolio(["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"], account_size=10_000))
```

## 信号引擎概要

- 趋势（1D + 4H）：EMA 金叉/死叉、MACD、SuperTrend、布林带、Ichimoku —— 按符号与置信度计算并归一化为 [−5, +5]
- 成交量与情绪（4H + 1H）：成交量突破、资金费率、持仓变化、订单簿、交易流 —— 符号×置信度 → 归一化 [−5, +5]
- 振荡器：RSI(14) 在 4H 与 1H 上的表现 —— 符号×置信度 → 归一化 [−5, +5]
- 市场状态：ADX(14)、ATR 扩张、成交量比率 —— 选择动态权重（趋势/震荡/高波动/低流动/正常）
- 强平热力图：`liquidation-orders`（仅 SWAP）作为补充证据，不计入得分

最终得分计算：`(Trend × w_trend + Volume × w_vol + Oscillator × w_osc) × 2` → 范围 [−10, +10]

## 运行测试

```bash
python3 -m pytest tests/ -v
```

## Skill 文件

`signal_skill.md` 是供 GitHub Copilot / AI 代理使用的技能定义。参见 `signal_skill.md` 了解完整协议，包括强制性的链路思路计算规则和自检清单。

## 许可

MIT
