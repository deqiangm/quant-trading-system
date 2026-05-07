#!/usr/bin/env python3
"""
Quant Options Tool — US stock options chain data, Black-Scholes Greeks,
option pricing, strategy P&L analysis, and implied volatility surface.

Actions:
 chain      — Get options chain for a stock (calls, puts, or both)
 expiries   — List available expiry dates for a stock
 greeks     — Calculate Black-Scholes Greeks for an option
 pricing    — Price an option using Black-Scholes
 strategy   — Calculate P&L for common options strategies
 volatility — Get implied volatility surface data

Supported strategies:
 covered_call, protective_put, bull_call_spread, bear_put_spread,
 iron_condor, straddle, strangle, custom
"""

import json
import logging
import math
from datetime import datetime, date
from math import log, sqrt, exp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

def _check_yfinance():
    """Return True if yfinance is importable."""
    try:
        import yfinance  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Black-Scholes pure-Python implementation
# ---------------------------------------------------------------------------

def _norm_cdf(x):
    """Standard normal cumulative distribution function."""
    return (1.0 + math.erf(x / sqrt(2.0))) / 2.0


def _norm_pdf(x):
    """Standard normal probability density function."""
    return exp(-0.5 * x * x) / sqrt(2.0 * math.pi)


def _bs_d1(S, K, T, r, q, sigma):
    """Calculate d1 in the Black-Scholes formula."""
    if T <= 0 or sigma <= 0:
        return 0.0
    return (log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))


def _bs_price(S, K, T, r, q, sigma, option_type):
    """Black-Scholes option price.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry in years
        r: Risk-free rate
        q: Dividend yield
        sigma: Volatility (annualized, 0-1 scale)
        option_type: "call" or "put"
    """
    if T <= 0:
        return max(S - K, 0) if option_type == "call" else max(K - S, 0)
    if sigma <= 0:
        # Zero vol: option is worth intrinsic discounted
        if option_type == "call":
            return max(S * exp(-q * T) - K * exp(-r * T), 0)
        else:
            return max(K * exp(-r * T) - S * exp(-q * T), 0)

    d1 = _bs_d1(S, K, T, r, q, sigma)
    d2 = d1 - sigma * sqrt(T)

    if option_type == "call":
        return S * exp(-q * T) * _norm_cdf(d1) - K * exp(-r * T) * _norm_cdf(d2)
    else:
        return K * exp(-r * T) * _norm_cdf(-d2) - S * exp(-q * T) * _norm_cdf(-d1)


def _bs_greeks(S, K, T, r, q, sigma, option_type):
    """Black-Scholes Greeks: delta, gamma, theta, vega, rho.

    Returns dict with rounded values.
    theta is per-day (divided by 365), vega per 1% vol, rho per 1% rate.
    """
    if T <= 0:
        T = 1e-10
    if sigma <= 0:
        sigma = 1e-10

    d1 = _bs_d1(S, K, T, r, q, sigma)
    d2 = d1 - sigma * sqrt(T)

    if option_type == "call":
        delta = exp(-q * T) * _norm_cdf(d1)
        theta = (
            -S * exp(-q * T) * _norm_pdf(d1) * sigma / (2 * sqrt(T))
            - r * K * exp(-r * T) * _norm_cdf(d2)
            + q * S * exp(-q * T) * _norm_cdf(d1)
        ) / 365
    else:
        delta = exp(-q * T) * (_norm_cdf(d1) - 1)
        theta = (
            -S * exp(-q * T) * _norm_pdf(d1) * sigma / (2 * sqrt(T))
            + r * K * exp(-r * T) * _norm_cdf(-d2)
            - q * S * exp(-q * T) * _norm_cdf(-d1)
        ) / 365

    gamma = exp(-q * T) * _norm_pdf(d1) / (S * sigma * sqrt(T))
    vega = S * exp(-q * T) * _norm_pdf(d1) * sqrt(T) / 100  # per 1% vol change
    rho = K * T * exp(-r * T) * _norm_cdf(d2 if option_type == "call" else -d2) / 100  # per 1% rate

    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 4),
        "theta": round(theta, 4),
        "vega": round(vega, 4),
        "rho": round(rho, 4),
    }


# ---------------------------------------------------------------------------
# Helper: compute time to expiry from expiry date string
# ---------------------------------------------------------------------------

def _time_to_expiry(expiry_str: str) -> float:
    """Parse 'YYYY-MM-DD' and return (expiry_date - today).days / 365.0."""
    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    today = date.today()
    days = (expiry_date - today).days
    return max(days / 365.0, 0.0)


# ---------------------------------------------------------------------------
# Helper: fetch current spot price via yfinance
# ---------------------------------------------------------------------------

def _fetch_spot_price(symbol: str) -> float | None:
    """Fetch the current spot price for a symbol via yfinance."""
    import yfinance as yf
    try:
        tk = yf.Ticker(symbol)
        info = tk.info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price is None:
            # Fallback: get from fast_info or history
            hist = tk.history(period="1d")
            if not hist.empty:
                price = hist["Close"].iloc[-1]
        return float(price) if price else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helper: fetch IV from yfinance chain for a given strike
# ---------------------------------------------------------------------------

def _fetch_implied_vol(symbol: str, expiry: str, strike: float, option_type: str) -> float | None:
    """Try to fetch implied volatility from yfinance for a specific option."""
    import yfinance as yf
    try:
        tk = yf.Ticker(symbol)
        chain = tk.option_chain(expiry)
        df = chain.calls if option_type == "call" else chain.puts
        row = df[df["strike"] == strike]
        if not row.empty:
            iv = row.iloc[0].get("impliedVolatility")
            if iv is not None and iv == iv:  # NaN check
                return float(iv)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Action: chain — Get options chain
# ---------------------------------------------------------------------------

def _action_chain(symbol: str, expiry: str | None, option_type: str) -> str:
    import yfinance as yf

    try:
        tk = yf.Ticker(symbol)
        expiries = tk.options
        if not expiries:
            return tool_error(f"No options data available for '{symbol}'")

        if expiry is None:
            expiry = expiries[0]
        elif expiry not in expiries:
            return tool_error(
                f"Expiry '{expiry}' not available for '{symbol}'. "
                f"Available: {list(expiries)[:5]}... Use action='expiries' for full list."
            )

        chain = tk.option_chain(expiry)
    except Exception as e:
        return tool_error(f"Failed to fetch options chain for '{symbol}': {e}")

    def _df_to_list(df, fields):
        """Convert a yfinance options DataFrame to a list of dicts."""
        result = []
        for _, row in df.iterrows():
            entry = {}
            for f in fields:
                val = row.get(f)
                if val is not None and val == val:  # NaN check
                    if hasattr(val, "item"):
                        val = val.item()  # numpy scalar -> python
                    entry[f] = val
            result.append(entry)
        return result

    call_fields = [
        "contractSymbol", "strike", "lastPrice", "bid", "ask",
        "volume", "openInterest", "impliedVolatility", "itm",
    ]
    put_fields = call_fields  # same structure

    calls_list = _df_to_list(chain.calls, call_fields) if option_type in ("call", "both") else []
    puts_list = _df_to_list(chain.puts, put_fields) if option_type in ("put", "both") else []

    # Round implied volatility for readability
    for entry in calls_list + puts_list:
        if entry.get("impliedVolatility") is not None:
            entry["impliedVolatility"] = round(entry["impliedVolatility"], 4)

    return tool_result({
        "status": "ok",
        "symbol": symbol,
        "expiry": expiry,
        "calls": calls_list,
        "puts": puts_list,
    })


# ---------------------------------------------------------------------------
# Action: expiries — List available expiry dates
# ---------------------------------------------------------------------------

def _action_expiries(symbol: str) -> str:
    import yfinance as yf

    try:
        tk = yf.Ticker(symbol)
        expiries = tk.options
        if not expiries:
            return tool_error(f"No options data available for '{symbol}'")
    except Exception as e:
        return tool_error(f"Failed to fetch expiries for '{symbol}': {e}")

    return tool_result({
        "status": "ok",
        "symbol": symbol,
        "expiries": list(expiries),
        "count": len(expiries),
    })


# ---------------------------------------------------------------------------
# Action: greeks — Calculate Black-Scholes Greeks
# ---------------------------------------------------------------------------

def _action_greeks(args: dict) -> str:
    symbol = args.get("symbol")
    strike = args.get("strike")
    expiry = args.get("expiry")
    option_type = args.get("option_type", "call")
    spot_price = args.get("spot_price")
    risk_free_rate = args.get("risk_free_rate", 0.05)
    dividend_yield = args.get("dividend_yield", 0.0)

    if not symbol or strike is None or not expiry:
        return tool_error("'symbol', 'strike', and 'expiry' are required for greeks action.")
    if option_type not in ("call", "put"):
        return tool_error("option_type must be 'call' or 'put' for greeks action.")

    # Auto-fetch spot price if not provided
    if spot_price is None:
        spot_price = _fetch_spot_price(symbol)
        if spot_price is None:
            return tool_error(f"Could not fetch spot price for '{symbol}'. Provide spot_price manually.")

    T = _time_to_expiry(expiry)
    if T <= 0:
        return tool_error(f"Expiry '{expiry}' is in the past or today.")

    # Try to get IV from yfinance
    iv = _fetch_implied_vol(symbol, expiry, float(strike), option_type)
    if iv is None:
        # Use a reasonable fallback (30%) if IV not available
        iv = 0.30

    greeks = _bs_greeks(float(spot_price), float(strike), T, float(risk_free_rate), float(dividend_yield), iv, option_type)
    bs_price = _bs_price(float(spot_price), float(strike), T, float(risk_free_rate), float(dividend_yield), iv, option_type)

    return tool_result({
        "status": "ok",
        "symbol": symbol,
        "strike": float(strike),
        "expiry": expiry,
        "option_type": option_type,
        "spot_price": round(float(spot_price), 4),
        "time_to_expiry_years": round(T, 6),
        "risk_free_rate": risk_free_rate,
        "dividend_yield": dividend_yield,
        "greeks": greeks,
        "bs_price": round(bs_price, 4),
        "implied_vol": round(iv, 4),
    })


# ---------------------------------------------------------------------------
# Action: pricing — Price an option using Black-Scholes
# ---------------------------------------------------------------------------

def _action_pricing(args: dict) -> str:
    spot_price = args.get("spot_price")
    strike = args.get("strike")
    T = args.get("time_to_expiry_years")
    risk_free_rate = args.get("risk_free_rate", 0.05)
    dividend_yield = args.get("dividend_yield", 0.0)
    volatility = args.get("volatility")
    option_type = args.get("option_type", "call")

    if spot_price is None or strike is None or T is None or volatility is None:
        return tool_error(
            "'spot_price', 'strike', 'time_to_expiry_years', and 'volatility' "
            "are required for pricing action."
        )
    if option_type not in ("call", "put"):
        return tool_error("option_type must be 'call' or 'put'.")

    S = float(spot_price)
    K = float(strike)
    t = float(T)
    r = float(risk_free_rate)
    q = float(dividend_yield)
    sigma = float(volatility)

    price = _bs_price(S, K, t, r, q, sigma, option_type)
    greeks = _bs_greeks(S, K, t, r, q, sigma, option_type)

    return tool_result({
        "status": "ok",
        "price": round(price, 4),
        "spot_price": S,
        "strike": K,
        "time_to_expiry_years": t,
        "risk_free_rate": r,
        "dividend_yield": q,
        "volatility": sigma,
        "option_type": option_type,
        "greeks": greeks,
    })


# ---------------------------------------------------------------------------
# Action: strategy — Calculate P&L for options strategies
# ---------------------------------------------------------------------------

def _option_payoff_at_expiry(spot: float, strike: float, option_type: str, direction: str, premium: float, quantity: int) -> float:
    """Calculate payoff for a single option leg at expiry.

    Args:
        spot: Spot price at expiry
        strike: Strike price
        option_type: "call" or "put"
        direction: "buy" or "sell"
        premium: Option premium paid/received
        quantity: Number of contracts
    """
    if option_type == "call":
        intrinsic = max(spot - strike, 0)
    else:
        intrinsic = max(strike - spot, 0)

    if direction == "buy":
        pnl = (intrinsic - premium) * quantity * 100
    else:  # sell
        pnl = (premium - intrinsic) * quantity * 100

    return pnl


def _stock_payoff_at_expiry(spot: float, entry_price: float, direction: str, quantity: int) -> float:
    """Calculate P&L for stock position at expiry.

    Args:
        spot: Spot price at expiry
        entry_price: Entry price of stock
        direction: "buy" or "sell"
        quantity: Number of shares
    """
    if direction == "buy":
        pnl = (spot - entry_price) * quantity
    else:  # sell
        pnl = (entry_price - spot) * quantity
    return pnl


def _compute_strategy_payoff(legs: list, stock_legs: list, spot_prices: list) -> list:
    """Compute total P&L at each spot price for given legs.

    Args:
        legs: List of option leg dicts with option_type, strike, direction, premium, quantity
        stock_legs: List of stock leg dicts with entry_price, direction, quantity
        spot_prices: List of spot prices at expiry

    Returns:
        List of P&L values corresponding to spot_prices
    """
    pnl_list = []
    for spot in spot_prices:
        total_pnl = 0.0
        for leg in legs:
            total_pnl += _option_payoff_at_expiry(
                spot, leg["strike"], leg["option_type"],
                leg["direction"], leg["premium"], leg["quantity"]
            )
        for leg in stock_legs:
            total_pnl += _stock_payoff_at_expiry(
                spot, leg["entry_price"], leg["direction"], leg["quantity"]
            )
        pnl_list.append(round(total_pnl, 2))
    return pnl_list


def _find_breakeven_points(spot_prices: list, pnl_list: list) -> list:
    """Find approximate breakeven points where P&L crosses zero."""
    breakevens = []
    for i in range(1, len(spot_prices)):
        pnl_prev = pnl_list[i - 1]
        pnl_curr = pnl_list[i]
        if pnl_prev == 0:
            breakevens.append(round(spot_prices[i - 1], 2))
        elif pnl_curr == 0:
            breakevens.append(round(spot_prices[i], 2))
        elif pnl_prev * pnl_curr < 0:
            # Linear interpolation
            s_prev = spot_prices[i - 1]
            s_curr = spot_prices[i]
            # Solve: pnl_prev + (pnl_curr - pnl_prev) * x = 0
            if pnl_curr - pnl_prev != 0:
                frac = -pnl_prev / (pnl_curr - pnl_prev)
                be = s_prev + frac * (s_curr - s_prev)
                breakevens.append(round(be, 2))
    return breakevens


def _build_predefined_strategy(strategy_type: str, symbol: str, spot_price: float, args: dict) -> tuple:
    """Build legs for predefined strategy types.

    Returns:
        (option_legs, stock_legs) tuple
    """
    import yfinance as yf

    option_legs = []
    stock_legs = []

    try:
        tk = yf.Ticker(symbol)
        expiries = tk.options
        if not expiries:
            return None, None, f"No options data available for '{symbol}'"
        expiry = args.get("expiry", expiries[0])
        if expiry not in expiries:
            expiry = expiries[0]
        chain = tk.option_chain(expiry)
    except Exception as e:
        return None, None, f"Failed to fetch options data for '{symbol}': {e}"

    calls_df = chain.calls
    puts_df = chain.puts

    def _safe_premium(row, field="lastPrice"):
        """Safely extract a premium from a DataFrame row, handling NaN."""
        val = row.get(field)
        if val is not None and val == val:  # NaN check
            return float(val)
        # Fallback to bid/ask mid if lastPrice is NaN
        bid = row.get("bid")
        ask = row.get("ask")
        if bid is not None and ask is not None and bid == bid and ask == ask:
            return (float(bid) + float(ask)) / 2.0
        return 0.0

    def _find_nearest_strike(df, target_strike):
        """Find the strike in df closest to target_strike."""
        if df.empty:
            return None, None
        idx = (df["strike"] - target_strike).abs().idxmin()
        row = df.loc[idx]
        return float(row["strike"]), _safe_premium(row)

    def _find_otm_strike(df, spot, direction, pct=0.02):
        """Find an OTM strike by percentage away from spot.
        direction: 'up' for calls (higher strikes), 'down' for puts (lower strikes)
        pct: percentage away from spot (e.g. 0.02 = 2% OTM)
        """
        if df.empty:
            return None, None
        # Filter for OTM strikes only
        if direction == "up":
            target_strike = spot * (1 + pct)
            otm_df = df[df["strike"] >= spot].sort_values("strike")
        else:
            target_strike = spot * (1 - pct)
            otm_df = df[df["strike"] <= spot].sort_values("strike", ascending=False)

        if len(otm_df) == 0:
            return None, None

        # Find closest to target percentage
        idx = (otm_df["strike"] - target_strike).abs().idxmin()
        row = otm_df.loc[idx]
        return float(row["strike"]), _safe_premium(row)

    S = spot_price

    if strategy_type == "covered_call":
        # Buy 100 shares, sell 1 ATM call
        stock_legs.append({"entry_price": S, "direction": "buy", "quantity": 100})
        strike, premium = _find_nearest_strike(calls_df, S)
        if strike is None:
            return None, None, "No call options found for covered call"
        option_legs.append({
            "option_type": "call", "strike": strike, "expiry": expiry,
            "direction": "sell", "quantity": 1, "premium": premium,
        })

    elif strategy_type == "protective_put":
        # Buy 100 shares, buy 1 ATM put
        stock_legs.append({"entry_price": S, "direction": "buy", "quantity": 100})
        strike, premium = _find_nearest_strike(puts_df, S)
        if strike is None:
            return None, None, "No put options found for protective put"
        option_legs.append({
            "option_type": "put", "strike": strike, "expiry": expiry,
            "direction": "buy", "quantity": 1, "premium": premium,
        })

    elif strategy_type == "bull_call_spread":
        # Buy 1 lower strike call, sell 1 higher strike call
        lower_strike = args.get("lower_strike")
        upper_strike = args.get("upper_strike")
        if lower_strike and upper_strike:
            l_row = calls_df[calls_df["strike"] == float(lower_strike)]
            u_row = calls_df[calls_df["strike"] == float(upper_strike)]
            l_premium = _safe_premium(l_row.iloc[0]) if not l_row.empty else 0
            u_premium = _safe_premium(u_row.iloc[0]) if not u_row.empty else 0
        else:
            # Default: ATM and 2 strikes above
            lower_strike, l_premium = _find_nearest_strike(calls_df, S)
            upper_strike, u_premium = _find_otm_strike(calls_df, S, "up", pct=0.02)
            if upper_strike is None:
                return None, None, "Not enough call strikes for bull call spread"

        option_legs.append({
            "option_type": "call", "strike": float(lower_strike), "expiry": expiry,
            "direction": "buy", "quantity": 1, "premium": l_premium,
        })
        option_legs.append({
            "option_type": "call", "strike": float(upper_strike), "expiry": expiry,
            "direction": "sell", "quantity": 1, "premium": u_premium,
        })

    elif strategy_type == "bear_put_spread":
        # Buy 1 higher strike put, sell 1 lower strike put
        lower_strike = args.get("lower_strike")
        upper_strike = args.get("upper_strike")
        if lower_strike and upper_strike:
            l_row = puts_df[puts_df["strike"] == float(lower_strike)]
            u_row = puts_df[puts_df["strike"] == float(upper_strike)]
            l_premium = _safe_premium(l_row.iloc[0]) if not l_row.empty else 0
            u_premium = _safe_premium(u_row.iloc[0]) if not u_row.empty else 0
        else:
            # Default: ATM and 2 strikes below
            upper_strike, u_premium = _find_nearest_strike(puts_df, S)
            lower_strike, l_premium = _find_otm_strike(puts_df, S, "down", pct=0.02)
            if lower_strike is None:
                return None, None, "Not enough put strikes for bear put spread"

        option_legs.append({
            "option_type": "put", "strike": float(upper_strike), "expiry": expiry,
            "direction": "buy", "quantity": 1, "premium": u_premium,
        })
        option_legs.append({
            "option_type": "put", "strike": float(lower_strike), "expiry": expiry,
            "direction": "sell", "quantity": 1, "premium": l_premium,
        })

    elif strategy_type == "iron_condor":
        # Sell 1 OTM put + buy 1 further OTM put + sell 1 OTM call + buy 1 further OTM call
        short_put_strike, short_put_prem = _find_otm_strike(puts_df, S, "down", pct=0.02)
        long_put_strike, long_put_prem = _find_otm_strike(puts_df, S, "down", pct=0.04)
        short_call_strike, short_call_prem = _find_otm_strike(calls_df, S, "up", pct=0.02)
        long_call_strike, long_call_prem = _find_otm_strike(calls_df, S, "up", pct=0.04)

        if any(v is None for v in [short_put_strike, long_put_strike, short_call_strike, long_call_strike]):
            return None, None, "Not enough strikes for iron condor"

        option_legs.append({
            "option_type": "put", "strike": short_put_strike, "expiry": expiry,
            "direction": "sell", "quantity": 1, "premium": short_put_prem,
        })
        option_legs.append({
            "option_type": "put", "strike": long_put_strike, "expiry": expiry,
            "direction": "buy", "quantity": 1, "premium": long_put_prem,
        })
        option_legs.append({
            "option_type": "call", "strike": short_call_strike, "expiry": expiry,
            "direction": "sell", "quantity": 1, "premium": short_call_prem,
        })
        option_legs.append({
            "option_type": "call", "strike": long_call_strike, "expiry": expiry,
            "direction": "buy", "quantity": 1, "premium": long_call_prem,
        })

    elif strategy_type == "straddle":
        # Buy 1 ATM call + buy 1 ATM put
        call_strike, call_prem = _find_nearest_strike(calls_df, S)
        put_strike, put_prem = _find_nearest_strike(puts_df, S)
        if call_strike is None or put_strike is None:
            return None, None, "No ATM options found for straddle"
        option_legs.append({
            "option_type": "call", "strike": call_strike, "expiry": expiry,
            "direction": "buy", "quantity": 1, "premium": call_prem,
        })
        option_legs.append({
            "option_type": "put", "strike": put_strike, "expiry": expiry,
            "direction": "buy", "quantity": 1, "premium": put_prem,
        })

    elif strategy_type == "strangle":
        # Buy 1 OTM call + buy 1 OTM put
        call_strike, call_prem = _find_otm_strike(calls_df, S, "up", pct=0.02)
        put_strike, put_prem = _find_otm_strike(puts_df, S, "down", pct=0.02)
        if call_strike is None or put_strike is None:
            return None, None, "Not enough OTM strikes for strangle"
        option_legs.append({
            "option_type": "call", "strike": call_strike, "expiry": expiry,
            "direction": "buy", "quantity": 1, "premium": call_prem,
        })
        option_legs.append({
            "option_type": "put", "strike": put_strike, "expiry": expiry,
            "direction": "buy", "quantity": 1, "premium": put_prem,
        })

    elif strategy_type == "calendar_spread":
        # Sell near-term ATM, buy far-term ATM (same strike, different expiry)
        call_strike, call_prem = _find_nearest_strike(calls_df, S)
        if call_strike is None:
            return None, None, "No ATM call found for calendar spread"
        # Near-term: sell (short)
        option_legs.append({
            "option_type": "call", "strike": call_strike, "expiry": expiry,
            "direction": "sell", "quantity": 1, "premium": call_prem,
        })
        # Far-term: buy (long) — premium approximated as 1.3x near-term
        far_prem = call_prem * 1.3
        back_expiry = args.get("back_expiry", "")
        if not back_expiry:
            try:
                from datetime import datetime, timedelta
                dt = datetime.strptime(expiry, "%Y-%m-%d")
                back_expiry = (dt + timedelta(days=30)).strftime("%Y-%m-%d")
            except Exception:
                back_expiry = expiry
        option_legs.append({
            "option_type": "call", "strike": call_strike, "expiry": back_expiry,
            "direction": "buy", "quantity": 1, "premium": round(far_prem, 4),
            "note": "Far-term premium approximated (1.3x near-term)",
        })

    elif strategy_type == "butterfly":
        # Iron butterfly: sell ATM straddle + buy OTM strangle for wings
        atm_call_strike, atm_call_prem = _find_nearest_strike(calls_df, S)
        atm_put_strike, atm_put_prem = _find_nearest_strike(puts_df, S)
        wing_pct = args.get("wing_pct", 0.03)
        otm_call_strike, otm_call_prem = _find_otm_strike(calls_df, S, "up", pct=wing_pct)
        otm_put_strike, otm_put_prem = _find_otm_strike(puts_df, S, "down", pct=wing_pct)
        if any(v is None for v in [atm_call_strike, atm_put_strike, otm_call_strike, otm_put_strike]):
            return None, None, "Not enough strikes for butterfly"
        # Sell ATM straddle
        option_legs.append({
            "option_type": "call", "strike": atm_call_strike, "expiry": expiry,
            "direction": "sell", "quantity": 1, "premium": atm_call_prem,
        })
        option_legs.append({
            "option_type": "put", "strike": atm_put_strike, "expiry": expiry,
            "direction": "sell", "quantity": 1, "premium": atm_put_prem,
        })
        # Buy wing strangle for protection
        option_legs.append({
            "option_type": "call", "strike": otm_call_strike, "expiry": expiry,
            "direction": "buy", "quantity": 1, "premium": otm_call_prem,
        })
        option_legs.append({
            "option_type": "put", "strike": otm_put_strike, "expiry": expiry,
            "direction": "buy", "quantity": 1, "premium": otm_put_prem,
        })

    elif strategy_type == "vertical_credit_spread":
        # Bull put spread or bear call spread
        bias = args.get("bias", "bullish")
        spread_pct = args.get("spread_pct", 0.03)
        if bias == "bullish":
            short_strike, short_prem = _find_otm_strike(puts_df, S, "down", pct=spread_pct * 0.5)
            long_strike, long_prem = _find_otm_strike(puts_df, S, "down", pct=spread_pct)
            if short_strike is None or long_strike is None:
                return None, None, "Not enough OTM puts for bull put spread"
            option_legs.append({
                "option_type": "put", "strike": short_strike, "expiry": expiry,
                "direction": "sell", "quantity": 1, "premium": short_prem,
            })
            option_legs.append({
                "option_type": "put", "strike": long_strike, "expiry": expiry,
                "direction": "buy", "quantity": 1, "premium": long_prem,
            })
        else:
            short_strike, short_prem = _find_otm_strike(calls_df, S, "up", pct=spread_pct * 0.5)
            long_strike, long_prem = _find_otm_strike(calls_df, S, "up", pct=spread_pct)
            if short_strike is None or long_strike is None:
                return None, None, "Not enough OTM calls for bear call spread"
            option_legs.append({
                "option_type": "call", "strike": short_strike, "expiry": expiry,
                "direction": "sell", "quantity": 1, "premium": short_prem,
            })
            option_legs.append({
                "option_type": "call", "strike": long_strike, "expiry": expiry,
                "direction": "buy", "quantity": 1, "premium": long_prem,
            })

    elif strategy_type == "ratio_spread":
        # Buy 1 ATM + sell N OTM
        ratio_dir = args.get("ratio_dir", "call_ratio")
        ratio = int(args.get("ratio", 2))
        if ratio_dir == "call_ratio":
            long_strike, long_prem = _find_nearest_strike(calls_df, S)
            short_strike, short_prem = _find_otm_strike(calls_df, S, "up", pct=0.03)
            if long_strike is None or short_strike is None:
                return None, None, "Not enough call strikes for ratio spread"
            option_legs.append({
                "option_type": "call", "strike": long_strike, "expiry": expiry,
                "direction": "buy", "quantity": 1, "premium": long_prem,
            })
            option_legs.append({
                "option_type": "call", "strike": short_strike, "expiry": expiry,
                "direction": "sell", "quantity": ratio, "premium": short_prem,
            })
        else:
            long_strike, long_prem = _find_nearest_strike(puts_df, S)
            short_strike, short_prem = _find_otm_strike(puts_df, S, "down", pct=0.03)
            if long_strike is None or short_strike is None:
                return None, None, "Not enough put strikes for ratio spread"
            option_legs.append({
                "option_type": "put", "strike": long_strike, "expiry": expiry,
                "direction": "buy", "quantity": 1, "premium": long_prem,
            })
            option_legs.append({
                "option_type": "put", "strike": short_strike, "expiry": expiry,
                "direction": "sell", "quantity": ratio, "premium": short_prem,
            })

    return option_legs, stock_legs, None


def _action_strategy(args: dict) -> str:
    strategy_type = args.get("strategy_type")
    symbol = args.get("symbol")
    spot_price = args.get("spot_price")
    legs = args.get("legs", [])

    if not strategy_type:
        return tool_error("'strategy_type' is required for strategy action.")
    if not symbol and strategy_type != "custom":
        return tool_error("'symbol' is required for predefined strategies.")

    # Auto-fetch spot price if not provided
    if spot_price is None:
        spot_price = _fetch_spot_price(symbol)
        if spot_price is None:
            return tool_error(f"Could not fetch spot price for '{symbol}'. Provide spot_price manually.")
    spot_price = float(spot_price)

    option_legs = []
    stock_legs = []

    if strategy_type == "custom":
        if not legs:
            return tool_error("'legs' array is required for custom strategy.")
        for leg in legs:
            option_legs.append({
                "option_type": leg.get("option_type", "call"),
                "strike": float(leg.get("strike", 0)),
                "expiry": leg.get("expiry", ""),
                "direction": leg.get("direction", "buy"),
                "quantity": int(leg.get("quantity", 1)),
                "premium": float(leg.get("premium", 0)),
            })
    else:
        option_legs, stock_legs, err = _build_predefined_strategy(
            strategy_type, symbol, spot_price, args
        )
        if err:
            return tool_error(err)

    # Generate spot prices from -20% to +20% in 5% increments (9 points)
    pct_offsets = [-0.20, -0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15, 0.20]
    spot_prices = [round(spot_price * (1 + pct), 2) for pct in pct_offsets]

    # Compute payoff at each spot price
    pnl_list = _compute_strategy_payoff(option_legs, stock_legs, spot_prices)

    # Find breakeven points
    breakeven_points = _find_breakeven_points(spot_prices, pnl_list)

    # Compute max profit and max loss from the payoff curve
    # Use a finer grid for better estimates
    fine_offsets = [i / 100.0 for i in range(-40, 41, 1)]  # -40% to +40% in 1% steps
    fine_spots = [round(spot_price * (1 + pct), 2) for pct in fine_offsets]
    fine_pnl = _compute_strategy_payoff(option_legs, stock_legs, fine_spots)

    max_profit = max(fine_pnl) if fine_pnl else 0
    max_loss = min(fine_pnl) if fine_pnl else 0

    # Check if max profit / loss is theoretically unlimited
    # For strategies with unlimited upside (e.g., long stock, long call), the highest
    # fine grid point will keep increasing. We mark as unlimited if the last point
    # is the max and we're at +40%.
    if len(fine_pnl) > 1 and fine_pnl[-1] == max_profit and fine_pnl[-2] < max_profit:
        # Still increasing at boundary → report as large number, not string
        max_profit_val = round(max_profit, 2)
        max_profit_note = "theoretically_unlimited"
    else:
        max_profit_val = round(max_profit, 2)
        max_profit_note = None

    if len(fine_pnl) > 1 and fine_pnl[0] == max_loss and fine_pnl[1] > max_loss:
        max_loss_val = round(max_loss, 2)
        max_loss_note = "theoretically_unlimited"
    else:
        max_loss_val = round(max_loss, 2)
        max_loss_note = None

    # Build legs output
    all_legs_out = []
    for leg in option_legs:
        all_legs_out.append({
            "type": "option",
            "option_type": leg["option_type"],
            "strike": leg["strike"],
            "expiry": leg.get("expiry", ""),
            "direction": leg["direction"],
            "quantity": leg["quantity"],
            "premium": round(leg["premium"], 4),
        })
    for leg in stock_legs:
        all_legs_out.append({
            "type": "stock",
            "direction": leg["direction"],
            "quantity": leg["quantity"],
            "entry_price": round(leg["entry_price"], 4),
        })

    return tool_result({
        "status": "ok",
        "strategy_type": strategy_type,
        "symbol": symbol,
        "spot_price": round(spot_price, 4),
        "legs": all_legs_out,
        "max_profit": max_profit_val,
        "max_loss": max_loss_val,
        "max_profit_note": max_profit_note,
        "max_loss_note": max_loss_note,
        "breakeven_points": breakeven_points,
        "payoff_at_expiry": {
            "prices": spot_prices,
            "pnl": pnl_list,
        },
    })


# ---------------------------------------------------------------------------
# Action: volatility — Get implied volatility surface data
# ---------------------------------------------------------------------------

def _action_volatility(symbol: str, expiry: str | None) -> str:
    import yfinance as yf

    try:
        tk = yf.Ticker(symbol)
        expiries = tk.options
        if not expiries:
            return tool_error(f"No options data available for '{symbol}'")

        if expiry is None:
            expiry = expiries[0]
        elif expiry not in expiries:
            return tool_error(
                f"Expiry '{expiry}' not available for '{symbol}'. "
                f"Available: {list(expiries)[:5]}..."
            )

        chain = tk.option_chain(expiry)
    except Exception as e:
        return tool_error(f"Failed to fetch options data for '{symbol}': {e}")

    spot_price = _fetch_spot_price(symbol)
    if spot_price is None:
        return tool_error(f"Could not fetch spot price for '{symbol}'")

    surface = []
    calls_df = chain.calls
    puts_df = chain.puts

    # Get all unique strikes from both calls and puts
    all_strikes = sorted(set(calls_df["strike"].tolist() + puts_df["strike"].tolist()))

    for strike in all_strikes:
        strike = float(strike)
        moneyness = round(strike / spot_price, 4)

        iv_call = None
        iv_put = None
        vol_call = None
        vol_put = None
        oi_call = None
        oi_put = None

        # Call data
        call_rows = calls_df[calls_df["strike"] == strike]
        if not call_rows.empty:
            row = call_rows.iloc[0]
            iv = row.get("impliedVolatility")
            if iv is not None and iv == iv:
                iv_call = round(float(iv), 4)
            vol_val = row.get("volume")
            vol_call = int(vol_val) if vol_val is not None and vol_val == vol_val else 0
            oi_val = row.get("openInterest")
            oi_call = int(oi_val) if oi_val is not None and oi_val == oi_val else 0

        # Put data
        put_rows = puts_df[puts_df["strike"] == strike]
        if not put_rows.empty:
            row = put_rows.iloc[0]
            iv = row.get("impliedVolatility")
            if iv is not None and iv == iv:
                iv_put = round(float(iv), 4)
            vol_val = row.get("volume")
            vol_put = int(vol_val) if vol_val is not None and vol_val == vol_val else 0
            oi_val = row.get("openInterest")
            oi_put = int(oi_val) if oi_val is not None and oi_val == oi_val else 0

        surface.append({
            "strike": strike,
            "moneyness": moneyness,
            "iv_call": iv_call,
            "iv_put": iv_put,
            "volume_call": vol_call,
            "volume_put": vol_put,
            "oi_call": oi_call,
            "oi_put": oi_put,
        })

    return tool_result({
        "status": "ok",
        "symbol": symbol,
        "expiry": expiry,
        "spot_price": round(spot_price, 4),
        "surface": surface,
        "count": len(surface),
    })


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------

def _handle_quant_options(args: dict, **kw) -> str:
    """Dispatch quant_options actions."""
    action = args.get("action", "chain")
    symbol = args.get("symbol")
    expiry = args.get("expiry")
    option_type = args.get("option_type", "both")

    if action == "chain":
        if not symbol:
            return tool_error("'symbol' is required for chain action.")
        return _action_chain(symbol, expiry, option_type)

    elif action == "expiries":
        if not symbol:
            return tool_error("'symbol' is required for expiries action.")
        return _action_expiries(symbol)

    elif action == "greeks":
        return _action_greeks(args)

    elif action == "pricing":
        return _action_pricing(args)

    elif action == "strategy":
        return _action_strategy(args)

    elif action == "volatility":
        if not symbol:
            return tool_error("'symbol' is required for volatility action.")
        return _action_volatility(symbol, expiry)

    else:
        return tool_error(
            f"Unknown action '{action}'. Valid: chain, expiries, greeks, pricing, strategy, volatility"
        )


# ---------------------------------------------------------------------------
# Schema (OpenAI function-calling format)
# ---------------------------------------------------------------------------

QUANT_OPTIONS_SCHEMA = {
    "name": "quant_options",
    "description": (
        "US stock options chain data, Black-Scholes Greeks, pricing, strategy P&L analysis, "
        "and implied volatility surface. Supports covered calls, protective puts, spreads, "
        "iron condors, straddles, and strangles. "
        "Actions: 'chain' (options chain), 'expiries' (list expiry dates), "
        "'greeks' (Black-Scholes Greeks), 'pricing' (option pricing), "
        "'strategy' (strategy P&L analysis), 'volatility' (IV surface)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["chain", "expiries", "greeks", "pricing", "strategy", "volatility"],
                "description": (
                    "Action to perform: 'chain' for options chain data, "
                    "'expiries' for available expiry dates, 'greeks' for Black-Scholes Greeks, "
                    "'pricing' for option pricing, 'strategy' for P&L analysis of options strategies, "
                    "'volatility' for implied volatility surface data."
                ),
            },
            "symbol": {
                "type": "string",
                "description": "Stock ticker symbol (e.g. AAPL, SPY, TSLA)",
            },
            "expiry": {
                "type": "string",
                "description": "Option expiry date in YYYY-MM-DD format. Defaults to nearest available expiry.",
            },
            "option_type": {
                "type": "string",
                "enum": ["call", "put", "both"],
                "description": "Filter by option type. Default: 'both' (for chain action).",
            },
            "strike": {
                "type": "number",
                "description": "Strike price (required for greeks action)",
            },
            "spot_price": {
                "type": "number",
                "description": "Current spot price. Auto-fetched from yfinance if omitted.",
            },
            "risk_free_rate": {
                "type": "number",
                "description": "Risk-free interest rate (default: 0.05 for 5%)",
                "default": 0.05,
            },
            "dividend_yield": {
                "type": "number",
                "description": "Annual dividend yield (default: 0.0)",
                "default": 0.0,
            },
            "volatility": {
                "type": "number",
                "description": "Annual volatility for pricing (0-1 scale, e.g. 0.3 for 30%). Required for pricing action.",
            },
            "time_to_expiry_years": {
                "type": "number",
                "description": "Time to expiry in years. Required for pricing action.",
            },
            "strategy_type": {
                "type": "string",
"enum": [
"covered_call", "protective_put", "bull_call_spread",
"bear_put_spread", "iron_condor", "straddle",
"strangle", "calendar_spread", "butterfly",
"vertical_credit_spread", "ratio_spread", "custom",
],
                "description": (
                    "Options strategy type for strategy action. "
                    "Predefined strategies auto-construct legs from current market data. "
                    "Use 'custom' to provide legs manually."
                ),
            },
            "legs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "option_type": {"type": "string", "description": "'call' or 'put'"},
                        "strike": {"type": "number", "description": "Strike price"},
                        "expiry": {"type": "string", "description": "Expiry date YYYY-MM-DD"},
                        "direction": {"type": "string", "enum": ["buy", "sell"], "description": "Buy or sell"},
                        "quantity": {"type": "integer", "description": "Number of contracts"},
                        "premium": {"type": "number", "description": "Option premium per share"},
                    },
                },
                "description": "Option legs for custom strategy (required when strategy_type='custom')",
            },
            "lower_strike": {
                "type": "number",
                "description": "Lower strike for spreads (optional, auto-selected if omitted)",
            },
            "upper_strike": {
                "type": "number",
                "description": "Upper strike for spreads (optional, auto-selected if omitted)",
            },
        },
        "required": ["action"],
    },
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

from tools.registry import registry, tool_error, tool_result

registry.register(
    name="quant_options",
    toolset="quant",
    schema=QUANT_OPTIONS_SCHEMA,
    handler=_handle_quant_options,
    check_fn=_check_yfinance,
    requires_env=[],
    is_async=False,
    description="US stock options chain data, Black-Scholes Greeks, option pricing, strategy P&L analysis (covered call, protective put, spreads, iron condor, straddle, strangle), and implied volatility surface.",
    emoji="📈",
)
