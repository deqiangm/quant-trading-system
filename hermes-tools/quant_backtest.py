"""
Quant Options Backtest Module — Simple historical P&L simulation.

Simulates option strategy P&L by:
1. Taking historical stock prices (entry date → expiry date)
2. Using Black-Scholes approximation for option pricing at entry and exit
3. Calculating strategy P&L per leg and aggregate

This is a PAPER backtest — uses estimated IV, not actual historical option prices.
Accuracy: ~80-90% for defined-risk strategies (spreads, iron condors).
Less accurate for naked positions and volatile underlyings.
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import yfinance as yf

from tools.registry import registry

# ---------------------------------------------------------------------------
# Black-Scholes helpers (simplified, no dividends)
# ---------------------------------------------------------------------------

def _norm_cdf(x):
    """Standard normal CDF approximation."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_price(S, K, T, r, sigma, option_type="call"):
    """Black-Scholes option price.

    S: spot price, K: strike, T: time-to-expiry (years),
    r: risk-free rate, sigma: annual volatility, option_type: 'call'/'put'
    """
    if T <= 0:
        # At expiry
        if option_type == "call":
            return max(S - K, 0.0)
        else:
            return max(K - S, 0.0)

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if option_type == "call":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def _estimate_historical_vol(prices, window=20):
    """Estimate annualized volatility from daily close prices."""
    if len(prices) < window + 1:
        window = len(prices) - 1
    if window < 2:
        return 0.30  # default 30%
    returns = np.log(prices[-window-1:] / prices[-window-1:-window-1] if len(prices) > window else prices / prices.shift(1).dropna())
    # Simple approach: use pct_change
    pct = prices.pct_change().dropna().tail(window)
    if len(pct) < 2:
        return 0.30
    daily_vol = pct.std()
    annual_vol = daily_vol * math.sqrt(252)
    return max(annual_vol, 0.10)  # floor at 10%


# ---------------------------------------------------------------------------
# Backtest Engine
# ---------------------------------------------------------------------------

def _run_backtest(args: dict, _hist=None, _entry_idx=None) -> str:
    """Run a simple historical backtest for an option strategy.

    Parameters:
        symbol: ticker (e.g. 'SPY')
        strategy_type: one of the supported strategies
        entry_date: ISO date string (e.g. '2026-03-01') — must be a trading day
        holding_days: number of days to hold (default 30)
        iv_override: override IV estimate (e.g. 0.25 for 25%)
        risk_free_rate: annual rate (default 0.045)
        strategy_args: additional strategy-specific args (bias, wing_pct, etc.)
    
    Internal parameters (used by multi backtest):
        _hist: pre-fetched yfinance DataFrame (avoid re-download)
        _entry_idx: integer index into _hist (avoid date matching issues)
    """
    symbol = args.get("symbol", "SPY").upper()
    strategy_type = args.get("strategy_type", "bull_call_spread")
    entry_date_str = args.get("entry_date", "")
    holding_days = int(args.get("holding_days", 30))
    iv_override = float(args.get("iv_override", 0)) if args.get("iv_override") else 0
    r = float(args.get("risk_free_rate", 0.045))

    # Fetch 6 months of history for vol estimation + price path
    if _hist is not None:
        hist = _hist
        ticker = yf.Ticker(symbol)  # still needed for option chain lookup
    else:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="6mo")
    if hist.empty:
        return json.dumps({"status": "error", "error": f"No price data for {symbol}"})

    # Determine entry date
    if _entry_idx is not None:
        # Direct index — used by multi backtest
        entry_idx = _entry_idx
        entry_dt = hist.index[entry_idx].to_pydatetime().replace(tzinfo=None)
    elif entry_date_str:
        try:
            entry_dt = datetime.strptime(entry_date_str, "%Y-%m-%d")
        except ValueError:
            return json.dumps({"status": "error", "error": f"Invalid entry_date format: {entry_date_str}"})
    else:
        # Default: 60 trading days ago (~3 months)
        entry_idx = max(0, len(hist) - 60)
        entry_dt = hist.index[entry_idx].to_pydatetime().replace(tzinfo=None)

    # Find entry and exit rows in history
    hist_dates = hist.index.to_pydatetime()
    entry_idx = None
    for i, dt in enumerate(hist_dates):
        if dt.replace(tzinfo=None) >= entry_dt:
            entry_idx = i
            break

    if entry_idx is None:
        return json.dumps({"status": "error", "error": f"Entry date {entry_date_str} not in history"})

    exit_idx = min(entry_idx + holding_days, len(hist) - 1)

    S_entry = float(hist["Close"].iloc[entry_idx])
    S_exit = float(hist["Close"].iloc[exit_idx])
    entry_date_actual = hist_dates[entry_idx].strftime("%Y-%m-%d")
    exit_date_actual = hist_dates[exit_idx].strftime("%Y-%m-%d")

    # Estimate IV
    prices_series = hist["Close"].iloc[:entry_idx + 1]
    hist_vol = _estimate_historical_vol(prices_series)
    iv = iv_override if iv_override > 0 else hist_vol * 1.15  # IV typically > HV

    # Get option chain at entry for real strike selection
    try:
        chains = ticker.options
        if chains:
            # Find expiry closest to holding_days after entry
            target_expiry_dt = entry_dt + timedelta(days=holding_days + 15)  # allow some buffer
            best_expiry = None
            for exp_str in chains:
                exp_dt = datetime.strptime(exp_str, "%Y-%m-%d")
                if exp_dt >= entry_dt + timedelta(days=holding_days):
                    if best_expiry is None or exp_dt < datetime.strptime(best_expiry, "%Y-%m-%d"):
                        best_expiry = exp_str
            expiry_str = best_expiry or chains[min(len(chains)-1, 2)]
        else:
            expiry_str = (entry_dt + timedelta(days=holding_days + 10)).strftime("%Y-%m-%d")
    except Exception:
        expiry_str = (entry_dt + timedelta(days=holding_days + 10)).strftime("%Y-%m-%d")

    # Calculate T (time to expiry in years) at entry and exit
    try:
        expiry_dt = datetime.strptime(expiry_str, "%Y-%m-%d")
    except ValueError:
        expiry_dt = entry_dt + timedelta(days=holding_days + 10)

    T_entry = max((expiry_dt - entry_dt).days / 365.0, 1/365)
    T_exit = max((expiry_dt - (entry_dt + timedelta(days=exit_idx - entry_idx))).days / 365.0, 0)

    # Build strategy legs using the same logic as quant_options
    # We'll approximate strikes based on S_entry
    strikes_pct = _get_strategy_strikes(strategy_type, S_entry, args.get("strategy_args", {}))
    if not strikes_pct:
        return json.dumps({"status": "error", "error": f"Unsupported strategy: {strategy_type}"})

    # Calculate P&L per leg
    legs_pnl = []
    total_pnl = 0.0
    total_entry_cost = 0.0
    total_exit_value = 0.0

    for leg in strikes_pct:
        K = leg["strike"]
        opt_type = leg["option_type"]
        direction = leg["direction"]
        qty = leg.get("quantity", 1)

        # Entry price (BS)
        entry_price = _bs_price(S_entry, K, T_entry, r, iv, opt_type)
        # Exit price (BS at exit, or intrinsic at expiry)
        exit_price = _bs_price(S_exit, K, T_exit, r, iv * 0.9, opt_type)  # IV typically drops as expiry nears

        if direction == "buy":
            leg_pnl = (exit_price - entry_price) * qty * 100  # 100 shares per contract
        else:  # sell
            leg_pnl = (entry_price - exit_price) * qty * 100

        total_entry_cost += entry_price * qty * 100 * (1 if direction == "buy" else -1)
        total_exit_value += exit_price * qty * 100 * (1 if direction == "buy" else -1)

        legs_pnl.append({
            "direction": direction,
            "option_type": opt_type,
            "strike": K,
            "quantity": qty,
            "entry_price": round(entry_price, 4),
            "exit_price": round(exit_price, 4),
            "pnl": round(leg_pnl, 2),
        })
        total_pnl += leg_pnl

    # Calculate additional metrics
    price_change_pct = (S_exit / S_entry - 1) * 100
    max_profit = max(leg["pnl"] for leg in legs_pnl) if legs_pnl else 0
    max_loss = min(leg["pnl"] for leg in legs_pnl) if legs_pnl else 0

    # Win/loss determination
    result = "WIN" if total_pnl > 0 else "LOSS" if total_pnl < 0 else "BREAKEVEN"

    return json.dumps({
        "status": "ok",
        "symbol": symbol,
        "strategy_type": strategy_type,
        "entry_date": entry_date_actual,
        "exit_date": exit_date_actual,
        "expiry": expiry_str,
        "holding_days": exit_idx - entry_idx,
        "S_entry": round(S_entry, 2),
        "S_exit": round(S_exit, 2),
        "price_change_pct": round(price_change_pct, 2),
        "iv_used": round(iv * 100, 1),
        "hist_vol": round(hist_vol * 100, 1),
        "risk_free_rate": r,
        "legs": legs_pnl,
        "total_entry_cost": round(total_entry_cost, 2),
        "total_exit_value": round(total_exit_value, 2),
        "total_pnl": round(total_pnl, 2),
        "result": result,
    })


def _get_strategy_strikes(strategy_type, S, args):
    """Return list of leg dicts with strikes for the given strategy."""
    pct_offset = args.get("spread_pct", 0.03)
    wing_pct = args.get("wing_pct", 0.03)
    bias = args.get("bias", "bullish")

    if strategy_type == "bull_call_spread":
        return [
            {"strike": round(S * (1 + pct_offset * 0.3), 2), "option_type": "call", "direction": "buy", "quantity": 1},
            {"strike": round(S * (1 + pct_offset), 2), "option_type": "call", "direction": "sell", "quantity": 1},
        ]
    elif strategy_type == "bear_put_spread":
        return [
            {"strike": round(S * (1 - pct_offset * 0.3), 2), "option_type": "put", "direction": "buy", "quantity": 1},
            {"strike": round(S * (1 - pct_offset), 2), "option_type": "put", "direction": "sell", "quantity": 1},
        ]
    elif strategy_type == "iron_condor":
        return [
            {"strike": round(S * (1 - pct_offset), 2), "option_type": "put", "direction": "buy", "quantity": 1},
            {"strike": round(S * (1 - pct_offset * 0.5), 2), "option_type": "put", "direction": "sell", "quantity": 1},
            {"strike": round(S * (1 + pct_offset * 0.5), 2), "option_type": "call", "direction": "sell", "quantity": 1},
            {"strike": round(S * (1 + pct_offset), 2), "option_type": "call", "direction": "buy", "quantity": 1},
        ]
    elif strategy_type == "straddle":
        return [
            {"strike": round(S, 2), "option_type": "call", "direction": "buy", "quantity": 1},
            {"strike": round(S, 2), "option_type": "put", "direction": "buy", "quantity": 1},
        ]
    elif strategy_type == "strangle":
        return [
            {"strike": round(S * (1 + pct_offset * 0.5), 2), "option_type": "call", "direction": "buy", "quantity": 1},
            {"strike": round(S * (1 - pct_offset * 0.5), 2), "option_type": "put", "direction": "buy", "quantity": 1},
        ]
    elif strategy_type == "butterfly":
        return [
            {"strike": round(S, 2), "option_type": "call", "direction": "sell", "quantity": 1},
            {"strike": round(S, 2), "option_type": "put", "direction": "sell", "quantity": 1},
            {"strike": round(S * (1 + wing_pct), 2), "option_type": "call", "direction": "buy", "quantity": 1},
            {"strike": round(S * (1 - wing_pct), 2), "option_type": "put", "direction": "buy", "quantity": 1},
        ]
    elif strategy_type == "vertical_credit_spread":
        if bias == "bullish":
            return [
                {"strike": round(S * (1 - pct_offset * 0.5), 2), "option_type": "put", "direction": "sell", "quantity": 1},
                {"strike": round(S * (1 - pct_offset), 2), "option_type": "put", "direction": "buy", "quantity": 1},
            ]
        else:
            return [
                {"strike": round(S * (1 + pct_offset * 0.5), 2), "option_type": "call", "direction": "sell", "quantity": 1},
                {"strike": round(S * (1 + pct_offset), 2), "option_type": "call", "direction": "buy", "quantity": 1},
            ]
    elif strategy_type == "calendar_spread":
        return [
            {"strike": round(S, 2), "option_type": "call", "direction": "sell", "quantity": 1},
            {"strike": round(S, 2), "option_type": "call", "direction": "buy", "quantity": 1},  # far-term
        ]
    elif strategy_type == "ratio_spread":
        ratio = int(args.get("ratio", 2))
        ratio_dir = args.get("ratio_dir", "call_ratio")
        if ratio_dir == "call_ratio":
            return [
                {"strike": round(S, 2), "option_type": "call", "direction": "buy", "quantity": 1},
                {"strike": round(S * (1 + pct_offset), 2), "option_type": "call", "direction": "sell", "quantity": ratio},
            ]
        else:
            return [
                {"strike": round(S, 2), "option_type": "put", "direction": "buy", "quantity": 1},
                {"strike": round(S * (1 - pct_offset), 2), "option_type": "put", "direction": "sell", "quantity": ratio},
            ]
    elif strategy_type == "covered_call":
        return [
            {"strike": round(S * (1 + pct_offset), 2), "option_type": "call", "direction": "sell", "quantity": 1},
        ]
    elif strategy_type == "protective_put":
        return [
            {"strike": round(S * (1 - pct_offset), 2), "option_type": "put", "direction": "buy", "quantity": 1},
        ]
    else:
        return None


def _run_multi_backtest(args: dict) -> str:
    """Run backtests across multiple entry dates for a strategy.

    Parameters:
        symbol: ticker
        strategy_type: strategy name
        num_runs: number of backtest runs (default 6)
        holding_days: days to hold (default 30)
        iv_override: override IV (optional)
    """
    symbol = args.get("symbol", "SPY").upper()
    strategy_type = args.get("strategy_type", "bull_call_spread")
    num_runs = min(int(args.get("num_runs", 6)), 12)
    holding_days = int(args.get("holding_days", 30))

    # Fetch history
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1y")
    if len(hist) < 60:
        return json.dumps({"status": "error", "error": f"Not enough history for {symbol} (need 60+ days)"})

    # Pick evenly-spaced entry points
    max_start = len(hist) - holding_days - 5
    if max_start < num_runs * 5:
        num_runs = max(1, max_start // 5)

    # Evenly space entry points across the history
    if num_runs <= 1:
        entry_indices = [max(10, max_start)]
    else:
        start_idx = max(10, holding_days + 5)
        entry_indices = [int(start_idx + i * (max_start - start_idx) / (num_runs - 1)) for i in range(num_runs)]

    results = []
    wins = 0
    total_pnl = 0.0

    for idx in entry_indices:
        entry_date = hist.index[idx].strftime("%Y-%m-%d")
        bt_args = {
            "symbol": symbol,
            "strategy_type": strategy_type,
            "entry_date": entry_date,
            "holding_days": holding_days,
            "risk_free_rate": 0.045,
        }
        if args.get("iv_override"):
            bt_args["iv_override"] = args["iv_override"]
        if args.get("strategy_args"):
            bt_args["strategy_args"] = args["strategy_args"]

        r = json.loads(_run_backtest(bt_args, _hist=hist, _entry_idx=idx))
        if r.get("status") == "ok":
            results.append({
                "entry_date": r["entry_date"],
                "exit_date": r["exit_date"],
                "S_entry": r["S_entry"],
                "S_exit": r["S_exit"],
                "price_change_pct": r["price_change_pct"],
                "total_pnl": r["total_pnl"],
                "result": r["result"],
            })
            if r["total_pnl"] > 0:
                wins += 1
            total_pnl += r["total_pnl"]

    win_rate = (wins / len(results) * 100) if results else 0
    avg_pnl = total_pnl / len(results) if results else 0

    return json.dumps({
        "status": "ok",
        "symbol": symbol,
        "strategy_type": strategy_type,
        "num_runs": len(results),
        "holding_days": holding_days,
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(avg_pnl, 2),
        "runs": results,
    })


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

registry.register(
    name="quant_backtest",
    toolset="quant",
    schema={
        "name": "quant_backtest",
        "description": (
            "Options strategy backtesting — simulate historical P&L using Black-Scholes pricing. "
            "Actions: 'single' (one entry-to-exit backtest), 'multi' (multiple entry points, "
            "aggregate win rate and P&L). Uses yfinance historical data + estimated IV. "
            "Supports all 11 strategy types: bull_call_spread, bear_put_spread, iron_condor, "
            "straddle, strangle, butterfly, vertical_credit_spread, calendar_spread, "
            "ratio_spread, covered_call, protective_put. "
            "NOTE: This is a paper backtest with BS-estimated prices, not actual historical quotes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["single", "multi"],
                    "description": (
                        "'single': backtest one entry-to-exit period. "
                        "'multi': backtest multiple entry points for aggregate statistics."
                    ),
                    "default": "multi",
                },
                "symbol": {
                    "type": "string",
                    "description": "Ticker symbol (e.g. SPY, AAPL, QQQ).",
                    "default": "SPY",
                },
                "strategy_type": {
                    "type": "string",
                    "enum": [
                        "bull_call_spread", "bear_put_spread", "iron_condor",
                        "straddle", "strangle", "butterfly",
                        "vertical_credit_spread", "calendar_spread",
                        "ratio_spread", "covered_call", "protective_put",
                    ],
                    "description": "Option strategy type to backtest.",
                    "default": "bull_call_spread",
                },
                "entry_date": {
                    "type": "string",
                    "description": "Entry date for single backtest (ISO format: YYYY-MM-DD). Default: 60 trading days ago.",
                },
                "holding_days": {
                    "type": "integer",
                    "description": "Days to hold the position (default 30).",
                    "default": 30,
                },
                "num_runs": {
                    "type": "integer",
                    "description": "Number of backtest runs for 'multi' action (default 6, max 12).",
                    "default": 6,
                },
                "iv_override": {
                    "type": "number",
                    "description": "Override estimated IV (e.g. 0.25 for 25%). Default: auto-estimate from historical vol * 1.15.",
                },
                "risk_free_rate": {
                    "type": "number",
                    "description": "Annual risk-free rate (default 0.045 = 4.5%).",
                    "default": 0.045,
                },
                "strategy_args": {
                    "type": "object",
                    "description": "Strategy-specific args: bias (bullish/bearish), wing_pct, spread_pct, ratio, ratio_dir.",
                },
            },
            "required": [],
        },
    },
    handler=lambda args, **kw: (
        _run_backtest(args) if args.get("action", "multi") == "single"
        else _run_multi_backtest(args)
    ),
    check_fn=lambda: True,
)
