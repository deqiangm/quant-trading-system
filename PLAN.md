# Quant Trading System — Implementation Plan

## Architecture: Hermes Agent Adaptation (Route B)

Build an LLM-driven trading system on the Hermes Agent scaffold, using custom quant tools for market data, technical analysis, paper trading, and decision journaling.

---

## Phase 1: Thinnest Viable Slice ✅ COMPLETE

| # | Component | File | Status |
|---|-----------|------|--------|
| 1 | quant_data tool | tools/quant_data.py | ✅ OKX CCXT market data |
| 2 | quant_indicators tool | tools/quant_indicators.py | ✅ Pure-Python SMA/EMA/RSI/MACD/BB/ATR |
| 3 | quant_execute tool | tools/quant_execute.py | ✅ Paper trading SQLite |
| 4 | quant_journal tool | tools/quant_journal.py | ✅ Decision logging SQLite |
| 5 | momentum SKILL | skills/finance/btc-momentum-trading/ | ✅ 8-step workflow |
| 6 | Hermes integration | model_tools.py, toolsets.py | ✅ 4 tools registered |
| 7 | E2E test | Verified 2026-05-02 | ✅ All steps pass |
| 8 | Cron job | btc-momentum-trader (every 4h) | ✅ Running |

---

## Phase 2: Enhancement Pipeline ✅ COMPLETE

### P2.1: SafetyShell ✅

| Feature | Implementation | Verified |
|---------|---------------|----------|
| Stop-loss tracking | `stop_loss_price` column in positions; auto-set at entry - 1.5x ATR | ✅ |
| Stop-loss breach | `stop_check` action auto-sells when price < stop_loss_price | ✅ |
| Daily loss kill switch | 5% threshold, all orders rejected | ✅ (existing) |
| Consecutive loss cooldown | 3 losses → 4h cooldown, buy/sell blocked | ✅ |
| Max open positions | 3 positions max, 4th rejected | ✅ |

### P2.2: Multi-Symbol + Mean Reversion ✅

| Feature | Implementation | Verified |
|---------|---------------|----------|
| ETH/USDT, SOL/USDT | All tools accept any CCXT symbol | ✅ |
| Mean-reversion SKILL | skills/finance/mean-reversion-trading/ (10.9KB) | ✅ |
| Signal logic | RSI<30 + price<BB_lower → BUY; RSI>70 + price>BB_upper → SELL | ✅ |
| Multi-symbol docs | Symbol table with ATR ranges, precision | ✅ |

### P2.3: LLM Market Regime Detection ✅

| Feature | Implementation | Verified |
|---------|---------------|----------|
| ADX indicator | Pure-Python Wilder-style smoothed calculation | ✅ |
| ATR percentile | Current ATR as % of last 100 periods | ✅ |
| Regime action | quant_indicators(action="regime") → trending/ranging/volatile/neutral | ✅ |
| Adaptive weighting | SKILL Step 2.5: trending=1.0x, neutral=0.8x, ranging=0.6x, volatile=0.4x | ✅ |

### P2.4: Web Dashboard ✅

| Feature | Implementation | Verified |
|---------|---------------|----------|
| Portfolio Dashboard | Balance, positions, PnL, kill switch, cooldown status | ✅ |
| Equity Curve | SVG charts: balance over time + cumulative PnL | ✅ |
| Trade Journal | Decision entries with confidence bars, reasoning | ✅ |
| REST API | 7 endpoints: portfolio, positions, history, equity, journal, regime, trade_results | ✅ |
| Auto-refresh | 10s polling via JS setInterval | ✅ |
| Dark theme | CSS vars: #0d1117 bg, accent colors | ✅ |
| Tool registration | quant_dashboard in toolsets.py + model_tools.py | ✅ |
| Server | Port 8899, quant_dashboard(action="serve") | ✅ Running |

---

## Tool Summary (5 tools)

| Tool | Actions | DB |
|------|---------|----|
| quant_data | ticker, ohlcv, orderbook, markets, exchanges | — |
| quant_indicators | sma, ema, rsi, macd, bollinger, atr, regime, all | — |
| quant_execute | buy, sell, status, positions, history, balance, stop_check | paper_trading.db |
| quant_journal | add, query, review, update | journal.db |
| quant_dashboard | serve, status | reads both DBs |

---

## File Map

```
hermes-agent/
  tools/
    quant_data.py          # CCXT market data (ticker, ohlcv, orderbook, markets)
    quant_indicators.py    # SMA, EMA, RSI, MACD, Bollinger, ATR, ADX, Regime
    quant_execute.py       # Paper trading + SafetyShell (stop-loss, cooldown, max positions)
    quant_journal.py       # Decision journal + reflection loop
    quant_dashboard.py     # Web dashboard (aiohttp, port 8899)
  model_tools.py           # +5 quant tool imports
  toolsets.py              # +quant toolset with 5 tools

~/.hermes/skills/finance/
  btc-momentum-trading/SKILL.md    # 8-step momentum strategy (with regime)
  mean-reversion-trading/SKILL.md  # 7-step mean reversion strategy

~/.hermes/quant_trading/
  paper_trading.db         # Portfolio, orders, positions, daily_pnl, cooldown_state
  journal.db               # Decision journal entries
```

---

## Next: Phase 3 (Future Enhancements)

### Priority 1: Validation & Hardening
- [ ] Backtest-validation: run strategy against historical data, measure Sharpe/Sortino/max drawdown
- [ ] Walk-forward optimization: rolling window parameter tuning
- [ ] Stress test: extreme market scenarios (flash crash, liquidity dry-up)

### Priority 2: Advanced Strategies
- [ ] Breakout strategy (Donchian channels + volume confirmation)
- [ ] Pairs trading (cointegration-based, BTC-ETH spread)
- [ ] Options strategy (volatility skew arbitrage)

### Priority 3: Production Readiness
- [ ] Live trading: OKX API with real keys (QUANT_LIVE_TRADING_ENABLED=true)
- [ ] Risk budgeting: correlation-aware portfolio risk
- [ ] Alert system: Telegram notifications for trades, stop-losses, regime changes
- [ ] Performance attribution: strategy-level PnL breakdown

---

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Exchange | OKX | Binance geo-blocked (HTTP 451) |
| Mode | Paper trading only | No real API keys needed; SQLite-backed |
| Indicators | Pure-Python | No ta-lib dependency; portable |
| Route | B (Hermes adaptation) | LLM-driven > static backtest |
| Cron frequency | 4h | Balance between signal freshness and API limits |
| Max position | $5,000 | 5% of $100K portfolio; risk 2%/trade |
| Stop-loss | 1.5x ATR from entry | Volatility-adaptive; tighter in low-vol |
| Cooldown | 4h after 3 losses | Prevents revenge trading |
| Max positions | 3 | Diversification without over-extension |
| Regime weights | trending=1.0x, volatile=0.4x | Reduce exposure in uncertain markets |
| Dashboard | aiohttp self-contained | Zero frontend deps; 10s auto-refresh |
