"""
execution/ — OKX order execution layer.

Connects to okx-trade-cli / okx-trade-mcp to place orders based on
signals produced by engine.SignalEngine.

Usage (demo mode, no real orders):
    from execution import execute_signal
    execute_signal(report, account_size=10_000, mode="demo")

Usage (live mode, requires API credentials):
    execute_signal(report, account_size=10_000, mode="live")
"""
from .executor import execute_signal

__all__ = ["execute_signal"]
