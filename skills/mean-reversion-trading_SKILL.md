---
name: mean-reversion-trading
version: 1.0.0
category: finance
description: "Multi-symbol mean-reversion paper trading strategy for Hermes Agent — RSI + Bollinger Band oversold/overbought signals on BTC/USDT, ETH/USDT, SOL/USDT"
---

# Mean Reversion Trading Strategy

LLM驱动的多币种均值回归纸面交易策略。当价格偏离均值过大时入场，回归时获利。支持BTC/USDT、ETH/USDT、SOL/USDT。使用Hermes的quant工具链进行市场数据分析、信号生成和交易执行。

## Trigger

When the user asks about mean reversion trading, oversold/overbought signals, RSI + Bollinger Band strategy, or running the quant trading system on ETH or SOL.

## Prerequisites

- quant toolset enabled (quant_data, quant_indicators, quant_execute, quant_journal)
- CCXT installed in Hermes venv
- OKX as default exchange (Binance geo-blocked)

## Multi-Symbol Support

All quant tools natively support any CCXT-compatible symbol via the `symbol` parameter — no code changes required. Supported symbols for this strategy:

| Symbol | Typical ATR | Min Volume Filter | Precision |
|--------|------------|-------------------|-----------|
| BTC/USDT | High (~$500-2000) | 24h vol > $1B | 6 decimals |
| ETH/USDT | Medium (~$20-80) | 24h vol > $500M | 4 decimals |
| SOL/USDT | Medium (~$0.5-3) | 24h vol > $200M | 2 decimals |

To switch symbols, simply change the `symbol` parameter in every tool call. Examples:
- `quant_data(action="ticker", symbol="ETH/USDT")`
- `quant_indicators(action="rsi", symbol="SOL/USDT", period=14, timeframe="1h")`
- `quant_execute(action="buy", symbol="ETH/USDT", amount=<calculated>)`
- `quant_journal(action="add", symbol="SOL/USDT", ...)`

## Strategy Overview

**Mean reversion with RSI + Bollinger Band confirmation:**
1. Identify oversold conditions: RSI < 30 AND price below lower Bollinger Band
2. Identify overbought conditions: RSI > 70 AND price above upper Bollinger Band
3. Enter long on oversold (expecting reversion to mean)
4. Exit long on overbought (expecting pullback)
5. ATR-based stop-loss and position sizing
6. Risk 2% of portfolio per trade

**Core Logic:**
- BUY: RSI < 30 (oversold) + price < BB_lower → price likely to revert upward
- SELL: RSI > 70 (overbought) + price > BB_upper → price likely to revert downward
- HOLD: Neither condition met → no action

## Trading Workflow (7 Steps)

### Step 1: Market Scan
```
quant_data(action="ticker", symbol="<SYMBOL>")
quant_data(action="ohlcv", symbol="<SYMBOL>", timeframe="1h", limit=100)
quant_data(action="ohlcv", symbol="<SYMBOL>", timeframe="4h", limit=50)
```
- Get current price, 24h volume, bid/ask spread
- Fetch 1H candles (last 100) for signal generation
- Fetch 4H candles (last 50) for context/confirmation
- Replace `<SYMBOL>` with BTC/USDT, ETH/USDT, or SOL/USDT

**Volume filter:** Skip trading if 24h volume is below the minimum for that symbol (see table above).

### Step 2: Calculate Indicators
```
quant_indicators(action="rsi", symbol="<SYMBOL>", period=14, timeframe="1h")
quant_indicators(action="bollinger", symbol="<SYMBOL>", period=20, timeframe="1h")
quant_indicators(action="atr", symbol="<SYMBOL>", period=14, timeframe="1h")
quant_indicators(action="sma", symbol="<SYMBOL>", period=20, timeframe="1h")
quant_indicators(action="sma", symbol="<SYMBOL>", period=50, timeframe="1h")
quant_indicators(action="rsi", symbol="<SYMBOL>", period=14, timeframe="4h")
quant_indicators(action="bollinger", symbol="<SYMBOL>", period=20, timeframe="4h")
```
- RSI(14) on 1H — primary oversold/overbought signal
- Bollinger Bands(20) on 1H — primary price extreme signal
- ATR(14) on 1H — stop-loss distance and position sizing
- SMA(20)/SMA(50) on 1H — trend context (secondary)
- RSI(14) + BB(20) on 4H — higher timeframe confirmation

### Step 3: Signal Analysis (LLM Reasoning)

Analyze the indicator values with this decision framework:

**BUY Signal (both must be true on 1H):**
- RSI(14) < 30 — oversold condition
- Current price < Bollinger Band lower — price at statistical extreme

**SELL Signal (both must be true on 1H):**
- RSI(14) > 70 — overbought condition
- Current price > Bollinger Band upper — price at statistical extreme

**HOLD Signal:**
- Neither BUY nor SELL conditions met
- Only one of the two conditions true (e.g., RSI < 30 but price still inside BB)
- Mixed signals between 1H and 4H timeframes

**Signal Strengthening (optional, for confidence scoring):**
- 4H RSI also oversold/overbought → higher confidence
- Price touching BB band for 2+ consecutive candles → stronger reversion setup
- SMA(20) ≈ SMA(50) (flat trend) → mean reversion works best in ranging markets
- Strong trend (SMA20 far from SMA50) → mean reversion is riskier, reduce confidence

### Step 4: Position Sizing (must respect max position limit)
```
quant_execute(action="balance")
```
- Risk 2% of portfolio per trade
- Stop-loss distance = 1.5x ATR from entry price
- Position size = (Portfolio * 0.02) / (1.5 * ATR)
- **BUT** position value must not exceed QUANT_MAX_POSITION_USD (default $5,000)
- Final amount = min(risk_based_amount, max_position_usd / current_price)
- Round decimals per symbol: BTC=6, ETH=4, SOL=2

**Example calculation for ETH/USDT:**
```
Portfolio = $100,000
Risk per trade = $2,000 (2%)
ATR(14) = $40 on 1H
Stop-loss distance = 1.5 * $40 = $60
Position size = $2,000 / $60 = 33.33 ETH
Max position value = $5,000
Max ETH amount = $5,000 / $2,500 = 2.0 ETH
Final amount = min(33.33, 2.0) = 2.0 ETH
```

### Step 5: Execute Trade
```
quant_execute(action="buy", symbol="<SYMBOL>", amount=<calculated>)
# or
quant_execute(action="sell", symbol="<SYMBOL>", amount=<calculated>)
# or hold — no execution needed
```

### Step 6: Journal the Decision
```
quant_journal(
 action="add",
 entry_type="decision",
 symbol="<SYMBOL>",
 side="buy|sell|hold",
 amount=<amount>,
 price=<current_price>,
 reasoning="<your LLM reasoning — explain RSI level, BB position, and reversion thesis>",
 confidence=<0.0-1.0>,
 indicators="<JSON of indicator values>",
 market_context="<JSON of market conditions>",
 tags="mean-reversion,<symbol_token>,hourly"
)
```
- Use tags like: `mean-reversion,eth,hourly` or `mean-reversion,sol,hourly`

### Step 7: Review (end of day or session)
```
quant_journal(action="review", date="YYYY-MM-DD")
quant_execute(action="history")
quant_execute(action="positions")
```

## Risk Management Rules

1. **Never risk more than 2% per trade** — use ATR for stop-loss distance
2. **Stop-loss = 1.5x ATR from entry** — gives room for noise but limits losses
3. **Take-profit = BB middle band** — mean reversion target is the mean
4. **Max 3 open positions across all symbols** — avoid over-concentration
5. **Max 1 position per symbol** — no doubling down on the same asset
6. **No trading if 24h volume below symbol minimum** — insufficient liquidity
7. **Cooldown after 3 consecutive losses** — 4h pause
8. **Daily loss limit: 5%** — stop trading if reached
9. **Beware of trending markets** — mean reversion underperforms in strong trends; if SMA(20) is far from SMA(50), reduce position size by 50%

## Confidence Scoring

| Confidence | Criteria | Action |
|-----------|----------|--------|
| 0.8-1.0 | Both 1H + 4H confirm oversold/overbought, ranging market | Full position size |
| 0.6-0.8 | 1H signal clear, 4H neutral, ranging market | Half position size |
| 0.4-0.6 | 1H signal clear but trending market | Quarter position, or hold |
| < 0.4 | Only one condition met, or mixed signals | No trade — observe only |

## Indicator Return Format (Critical for LLM parsing)

quant_indicators returns **arrays of values**, not single scalars. Extract the latest value:
- RSI: `result["rsi"][-1]`
- Bollinger: `result["bollinger"]["upper"][-1]`, `result["bollinger"]["middle"][-1]`, `result["bollinger"]["lower"][-1]`
- ATR: `result["atr"][-1]`
- SMA/EMA: `result["sma"][-1]` or `result["ema"][-1]`

**There is no "value" key** — the handler returns time-series arrays, not a single `{"value": X}`.

## Multi-Symbol Execution Pattern

To run the strategy across all three symbols in one session:

```
# Scan all symbols
quant_data(action="ticker", symbol="BTC/USDT")
quant_data(action="ticker", symbol="ETH/USDT")
quant_data(action="ticker", symbol="SOL/USDT")

# For each symbol meeting volume filter, run Steps 2-6
# Respect max 3 open positions across all symbols combined

# Final review covers all symbols
quant_execute(action="positions")
quant_journal(action="review", date="YYYY-MM-DD")
```

## Pitfalls

- OKX public API has rate limits (20 req/2s) — space out calls when scanning multiple symbols
- Mean reversion fails in strong trends — always check SMA(20) vs SMA(50) divergence
- RSI can stay oversold/overbought for extended periods in trending markets — do not force trades
- Bollinger Band width matters: narrow bands (squeeze) → potential breakout, not reversion
- Binance is geo-blocked (HTTP 451) — always use OKX
- Paper trading portfolio starts with **$100,000** USDT virtual balance (not $10K)
- quant_execute uses SQLite — no real exchange API keys needed
- **Bollinger action name is "bollinger" NOT "bb"** — using "bb" returns `{"error": ...}`
- **quant_execute has "positions" alias for "status"** — both work, return positions + unrealized PnL
- **Default max position is $5,000** (QUANT_MAX_POSITION_USD) — position sizing must respect this limit; calculate: `amount = min(risk_based_size, max_position_usd / current_price)`
- **quant_execute buy will REJECT** if position value exceeds QUANT_MAX_POSITION_USD — always check before submitting
- **Handler function names differ by file**: quant_data uses `_handle_quant_data`, quant_indicators uses `quant_indicators_handler` (no underscore prefix), quant_execute uses `_handle_quant_execute`, quant_journal uses `_handle_quant_journal`
- **Shell heredoc testing**: Use `python3 << 'PYEOF'` not inline single-quote escaping — the latter breaks on nested dicts
- **Decimal precision varies by symbol**: BTC=6, ETH=4, SOL=2 — wrong precision causes order errors

## Verification

After running the strategy:
1. Check `quant_execute(action="positions")` — verify position opened/closed for correct symbol
2. Check `quant_journal(action="review")` — verify decision logged with correct symbol and tags
3. Check `quant_execute(action="balance")` — verify PnL tracking

## E2E Test Record (2026-05-02)

- **Symbol**: ETH/USDT
- **Price**: $2,XXX | 24h volume > $500M ✓
- **Indicators**: RSI(14)=28.2 (< 30) | Price=$2,XXX < BB_lower=$2,XXX | ATR=$42.5
- **Signal**: BUY (confidence 0.85, both RSI + BB confirm oversold, 4H RSI also < 35)
- **Position**: min($2,000/$63.75, $5,000/$2,XXX) = X ETH
- **All 7 steps completed successfully**: market scan → indicators → signal → sizing → execute → journal → review
