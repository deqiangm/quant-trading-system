# Quant Trading System — Hermes Integration Design

## Architecture: How Quant Tools Integrate with Hermes Agent

### Integration Chain

```
User/Cron/Skill Prompt
        ↓
┌─────────────────────────────────────┐
│  AIAgent (run_agent.py)             │
│  - System prompt + skill injection  │
│  - Conversation loop (max 90 iters) │
│  - Tool call dispatch               │
└──────────┬──────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  model_tools.py                     │
│  - _discover_tools() imports all    │
│    quant tool modules at startup    │
│  - get_tool_definitions() collects  │
│    schemas from registry            │
│  - handle_function_call() routes    │
│    to registry.dispatch()           │
└──────────┬──────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  tools/registry.py                  │
│  - Central dispatch table           │
│  - Each tool module calls           │
│    registry.register() at import    │
│  - dispatch() → handler(args)       │
└──────────┬──────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  Tool Implementation                │
│  quant_data.py    → CCXT API        │
│  quant_indicators → Pure-Python     │
│  quant_execute    → SQLite (paper)  │
│  quant_journal    → SQLite (log)    │
│  quant_dashboard  → aiohttp (web)   │
└─────────────────────────────────────┘
```

### Registration Flow (at import time)

```python
# tools/quant_data.py (at module level)
registry.register(
    name="quant_data",                    # Tool name for LLM
    toolset="quant",                      # Toolset grouping
    schema={                              # OpenAI function schema
        "name": "quant_data",
        "description": "Fetch crypto market data...",
        "parameters": { ... }
    },
    handler=lambda args, **kw: _handle_quant_data(args),
    check_fn=_check_ccxt,                 # Availability check
    requires_env=[],                      # No API key needed for OKX public
)
```

All 5 quant tools follow the same pattern. The `_discover_tools()` function
in `model_tools.py` imports each module, triggering `registry.register()`.
The LLM sees these as standard function-call tools.

### Toolset Configuration

```python
# toolsets.py
_HERMES_CORE_TOOLS = [
    ...,
    "quant_data", "quant_indicators", "quant_execute",
    "quant_journal", "quant_dashboard",
]

TOOLSETS = {
    "quant": {
        "description": "Quantitative trading: market data, indicators, paper trading, journaling, dashboard",
        "tools": ["quant_data", "quant_indicators", "quant_execute",
                  "quant_journal", "quant_dashboard"],
    },
}
```

Users enable/disable via `hermes tools` CLI or `config.yaml`:
```yaml
toolsets:
  quant: true
```

---

## End-to-End Workflow: Momentum Trading

Below is the complete data flow when the cron job (or user) triggers a
trading cycle. Each step is a **single tool call** from the LLM.

```
Time: Every 4 hours (cron) or user prompt
  │
  ├─ Step 1: MARKET SCAN
  │   quant_data(action="ticker", symbol="BTC/USDT", exchange="okx")
  │   quant_data(action="ohlcv", symbol="BTC/USDT", timeframe="1h", limit=100)
  │   → Returns: {last: 78135, percentage: -0.32, quoteVolume: 1.2B, ...}
  │   → Returns: {candles: [[ts,o,h,l,c,v], ...], count: 100}
  │
  ├─ Step 2: TECHNICAL INDICATORS
  │   quant_indicators(action="sma", symbol="BTC/USDT", period=20, timeframe="1h")
  │   quant_indicators(action="sma", symbol="BTC/USDT", period=50, timeframe="1h")
  │   quant_indicators(action="rsi", symbol="BTC/USDT", period=14, timeframe="1h")
  │   quant_indicators(action="macd", symbol="BTC/USDT", timeframe="1h")
  │   quant_indicators(action="bollinger", symbol="BTC/USDT", period=20, timeframe="1h")
  │   quant_indicators(action="atr", symbol="BTC/USDT", period=14, timeframe="1h")
  │   → Returns: {sma: [...], latest: 78406}
  │   → Returns: {rsi: [...], latest: 44.4}
  │   → Returns: {macd: {macd_line: [...], signal_line: [...], histogram: [...]}}
  │
  ├─ Step 2.5: REGIME DETECTION  ← Phase 2 addition
  │   quant_indicators(action="regime", symbol="BTC/USDT", timeframe="1h")
  │   → Returns: {regime: "trending", adx: 32.1, atr_percentile: 65,
  │                confidence_multiplier: 1.0}
  │   → LLM adjusts confidence: score * multiplier
  │
  ├─ Step 3: SIGNAL ANALYSIS (LLM reasoning, no tool call)
  │   LLM evaluates:
  │   - SMA(20) > SMA(50)? → bullish/bearish
  │   - EMA(12) > EMA(26)? → bullish/bearish
  │   - RSI in 40-70 zone? → momentum/oversold/overbought
  │   - MACD histogram > 0? → rising/falling
  │   - Price > BB middle? → above/below mean
  │   - Regime multiplier → adjust confidence
  │   → Decision: BUY / SELL / HOLD + confidence score
  │
  ├─ Step 4: RISK MANAGEMENT (LLM reasoning, no tool call)
  │   Position sizing:
  │   risk_amount = portfolio * 0.02
  │   position_size = risk_amount / ATR
  │   actual_amount = min(position * price, max_position)
  │
  ├─ Step 5: EXECUTE TRADE
  │   quant_execute(action="buy", symbol="BTC/USDT", amount=0.001, atr=500)
  │   → SafetyShell checks:
  │     ✓ Kill switch: daily loss < 5%?
  │     ✓ Cooldown: < 3 consecutive losses?
  │     ✓ Max positions: < 3 open?
  │   → Sets stop_loss_price = entry - 1.5 * ATR
  │   → Returns: {status: "filled", price: 78135, amount: 0.001,
  │                stop_loss_price: 77385, position_id: 42}
  │
  ├─ Step 6: SAFETY CHECK  ← Phase 2 addition
  │   quant_execute(action="stop_check")
  │   → Scans all positions with stop_loss_price
  │   → If current_price < stop_loss_price → auto-sell
  │   → Returns: {positions_scanned: 2, stop_losses_triggered: 0}
  │
  ├─ Step 7: JOURNAL DECISION
  │   quant_journal(action="add", entry_type="decision",
  │                 symbol="BTC/USDT", side="buy",
  │                 price=78135, amount=0.001,
  │                 reasoning="Momentum buy: 3/5 signals + trending regime",
  │                 confidence=0.80, indicators={...},
  │                 market_context={...}, tags="momentum,btc,hourly")
  │   → Returns: {id: 15, status: "logged"}
  │
  ├─ Step 8: DAILY REVIEW
  │   quant_journal(action="review")
  │   → Returns: {summary: {total_decisions: 5, total_pnl: -12.50,
  │                avg_confidence: 0.72, best_trade: ..., worst_trade: ...}}
  │
  └─ Step 9: DASHBOARD (optional, background)
      quant_dashboard(action="serve", port=8899)
      → Web UI auto-refreshes with latest data
```

### Data Flow Between Tools

```
quant_data ──(candles)──→ quant_indicators ──(values)──→ LLM reasoning
                                                         ↓
                                                    buy/sell/hold
                                                         ↓
                              quant_journal ←──(decision)── quant_execute
                                   ↓
                            quant_dashboard (reads both SQLite DBs)
```

Key insight: **quant_indicators does NOT call quant_data internally**.
The LLM orchestrates the flow — it fetches data, passes results to
indicators, reasons on outputs, and executes. This separation means:
1. Each tool is independently testable
2. The LLM can skip steps or change order
3. New strategies just change the reasoning prompt (SKILL.md)

### Skill Injection

Skills are loaded as **user messages** (not system prompt) to preserve
prompt caching. When the cron job or user activates a strategy:

```
Skill: btc-momentum-trading
  ↓
SKILL.md content → injected as user message
  ↓
LLM sees: "Follow this 8-step workflow..."
  ↓
LLM calls tools in the prescribed order
```

### Cron Automation

```
cronjob(schedule="every 4h",
        skills=["btc-momentum-trading"],
        prompt="Run BTC/USDT momentum strategy...")
  ↓
Every 4 hours:
  1. Fresh session (no chat context)
  2. Skill loaded → SKILL.md injected
  3. LLM executes 8-step workflow
  4. Tool calls → real market data + paper trades
  5. Decision journaled to SQLite
  6. Response delivered to Telegram
```

### Extending to Other Asset Classes

Current: CCXT (crypto only)
Future: Add data adapters per asset class

```python
# Hypothetical: quant_data.py with multi-asset support
def _handle_quant_data(args):
    asset_class = args.get("asset_class", "crypto")
    
    if asset_class == "crypto":
        return _fetch_ccxt(args)        # Current implementation
    elif asset_class == "stock":
        return _fetch_yfinance(args)    # yfinance adapter
    elif asset_class == "fx":
        return _fetch_oanda(args)       # OANDA adapter
    elif asset_class == "futures":
        return _fetch_ibkr(args)        # Interactive Brokers
```

The indicator, execution, and journal layers are asset-class agnostic.
Only quant_data needs a new adapter. quant_execute already has a
live-mode guard (QUANT_LIVE_TRADING_ENABLED) that would connect to
real broker APIs.

### Multi-Agent Future

```
┌─────────────────┐  ┌──────────────────┐  ┌─────────────────┐
│ Momentum Agent   │  │ Mean-Revert Agent │  │ Breakout Agent  │
│ (BTC 4h cron)    │  │ (ETH 4h cron)     │  │ (SOL 4h cron)   │
└───────┬──────────┘  └────────┬─────────┘  └────────┬────────┘
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Portfolio Manager   │
                    │ (daily cron)        │
                    │ - Correlation check │
                    │ - Risk budgeting    │
                    │ - Position sizing   │
                    └─────────────────────┘
```

Each strategy agent runs independently via cron, journals its decisions.
Portfolio Manager reads all journals, enforces portfolio-level constraints.
