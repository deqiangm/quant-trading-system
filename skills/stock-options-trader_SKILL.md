---
name: stock-options-trader
version: 1.1.0
category: finance
description: "LLM-driven autonomous stock & options paper trading — 5-phase protocol: situational awareness → LLM reasoning → strategy selection → risk check → reflection"
---

# Stock & Options Trader — LLM-Driven Autonomous Trading

Full autonomous trading loop: market intel → LLM reasoning → strategy selection → execution → reflection.
This skill is designed for cron job execution. The LLM IS the brain — it must think, not just follow rules.

## Trigger
Cron job runs every 4 hours during market hours (9:30-16:00 ET, Mon-Fri for stocks; 24/7 for crypto).

## Execution Protocol

### PHASE 1: Situational Awareness (Tools: quant_market_intel, quant_execute)
```
Step 1: quant_market_intel action=regime symbol=SPY asset_class=stock
 → Get market regime (trending/ranging/crisis/stressed/contrarian)
 
Step 2: quant_market_intel action=macro
 → Cross-asset: DXY, Gold, VIX, SPX, BTC, yields, credit
 
Step 3: quant_market_intel action=fear_greed
 → Crypto Fear & Greed Index

Step 4: quant_market_intel action=alpha_watchlist
 → Alpha V4 auto-rotating trade candidates (5 categories)
 → Check crash_warning_level and top picks
 → Use trade_candidates to find strategy-matched symbols

Step 5: quant_execute action=status
 → Current portfolio: positions, balances, daily P&L
```

### PHASE 2: LLM Reasoning (NO TOOLS — pure thinking)
The LLM must synthesize Phase 1 data and answer:

1. **REGIME VERDICT**: What is the dominant regime? (use composite_regime from Step 1)
2. **CROSS-ASSET SIGNALS**: What are the 2-3 most important cross-asset relationships right now?
3. **SENTIMENT vs PRICE**: Is sentiment aligned with price action, or divergent?
4. **PORTFOLIO RISK**: Am I over-exposed? Need to hedge? Need to reduce?
5. **OPPORTUNITY**: Based on regime + sentiment + IV levels, what strategy makes sense NOW?

**Decision Gate**: 
- If confidence < 0.5 → NO TRADE, log observation and exit
- If confidence 0.5-0.8 → Execute with HALF position size
- If confidence >= 0.8 → Execute with FULL position size (within risk limits)

### PHASE 2.5: Backtest Verification (MANDATORY before executing new strategies)
```
quant_backtest action=multi symbol=<target> strategy_type=<chosen_strategy> num_runs=6 holding_days=30
 → If win_rate < 40%: SKIP — negative expectancy
 → If win_rate 40-60%: proceed with 50% position size
 → If win_rate > 60%: proceed with normal sizing
 → If avg_pnl < 0: SKIP even if win_rate > 50% (losses too large)
```

### PHASE 3: Strategy Execution (if confidence >= 0.5)
Based on regime, choose ONE strategy:

#### Strategy A: Stock Momentum (regime=trending, confidence>=0.7)
```
quant_indicators action=all symbol=<target> asset_class=stock
 → Confirm: RSI 50-70, MACD bullish, price > SMA50
quant_market_intel action=news symbol=<target> limit=5
 → Confirm: no strongly negative news
quant_execute action=buy symbol=<target> amount=<risk_based> asset_class=stock
quant_execute action=set_stop_loss id=<pos_id> stop_price=<entry-1.5*ATR>
```

#### Strategy B: Covered Call (regime=ranging/neutral, IV rank > 30, holding stock)
```
quant_market_intel action=volatility symbol=<held_stock>
 → Confirm: IV rank > 30 (NOT just IV > 30% — need IV rank proxy)
quant_options action=chain symbol=<held_stock> expiry=<30-45 DTE>
 → Select 3-5% OTM call with good volume/OI
quant_execute action=option_sell symbol=<held_stock> option_type=call
 strike=<3-5% OTM> expiry=<nearest 30-45 DTE>
```
⚠️ **Do NOT use `quant_options strategy strategy_type=covered_call`** — it defaults to ATM + 0DTE which is useless. Always manually select strike and expiry.

#### Strategy C: Protective Put (regime=stressed/crisis, holding stock)
```
quant_market_intel action=volatility symbol=<held_stock>
 → If IV LOW: buy ATM put for full hedge
 → If IV HIGH: buy 5% OTM put (cheaper)
quant_execute action=option_buy symbol=<held_stock> option_type=put
 strike=<ATM or 5% OTM> expiry=<30-45 DTE>
```

#### Strategy D: Iron Condor on SPY (regime=ranging, VIX 15-25, IV rank > 30)
```
quant_market_intel action=volatility symbol=SPY
 → Confirm: IV rank > 30
quant_options action=chain symbol=SPY expiry=<30-45 DTE>
quant_execute action=option_sell symbol=SPY option_type=put strike=<-2% OTM>
quant_execute action=option_buy symbol=SPY option_type=put strike=<-4% OTM>
quant_execute action=option_sell symbol=SPY option_type=call strike=<+2% OTM>
quant_execute action=option_buy symbol=SPY option_type=call strike=<+4% OTM>
```

#### Strategy E: BTC Momentum (regime=trending for crypto)
```
quant_indicators action=all symbol=BTC/USDT asset_class=crypto
 → Confirm: RSI 50-70, MACD bullish
quant_execute action=buy symbol=BTC/USDT amount=<risk_based> asset_class=crypto
quant_execute action=set_stop_loss id=<pos_id> stop_price=<entry-1.5*ATR>
```

#### Strategy F: Calendar Spread (regime=ranging/neutral, IV low-mid)
```
quant_options action=strategy strategy_type=calendar_spread symbol=<target>
 → Sell near-term ATM call, buy far-term ATM call
 → Profit from theta decay differential (near-term decays faster)
 → Best when: flat price action expected, IV low (cheap to enter)
 → Risk: LIMITED to net debit paid
```

#### Strategy G: Iron Butterfly (regime=ranging, high IV, VIX>20)
```
quant_options action=strategy strategy_type=butterfly symbol=<target> wing_pct=0.03
 → Sell ATM straddle + buy OTM wings
 → High premium collection, defined risk
 → Best when: expect price to pin at current level, IV elevated
 → Risk: DEFINED (wing width - net credit)
 → WARNING: Requires precise timing — profit zone is narrow
```

#### Strategy H: Vertical Credit Spread (regime=leaning directional, moderate IV)
```
# Bullish lean → bull put spread
quant_options action=strategy strategy_type=vertical_credit_spread bias=bullish spread_pct=0.03
# Bearish lean → bear call spread
quant_options action=strategy strategy_type=vertical_credit_spread bias=bearish spread_pct=0.03
 → Sell closer-to-ATM, buy further OTM
 → Collect premium with defined risk
 → Best when: slight directional bias + IV moderately high
 → Risk: DEFINED (strike width - net credit)
```

#### Strategy I: Ratio Spread (regime=directional, HIGH confidence, IV low)
```
quant_options action=strategy strategy_type=ratio_spread ratio_dir=call_ratio ratio=2
 → Buy 1 ATM, sell 2 OTM
 → Low/no cost entry, leveraged directional play
 → Best when: strong conviction on direction, IV low
 → ⚠️ DANGER: One short leg is NAKED — unlimited risk if wrong
 → ONLY use with: confidence >= 0.8 AND tight stop on underlying
 → NEVER use in volatile/crisis regime
```

### PHASE 4: Risk Check (ALWAYS after execution)
```
quant_execute action=status → verify total portfolio risk
 → If risk > 10%: reduce smallest position
 → If positions > 3: don't add more
 → If daily loss > 5%: kill switch, stop trading
```

### PHASE 5: Reflection & Journal
```
quant_journal action=add entry_type=decision symbol=<traded_or_PORTFOLIO> side=<buy/sell/hold>
 reasoning="<LLM reasoning in 2-3 sentences>"
 confidence=<0-1> tags="<regime>,<action>"
```
⚠️ **Use `quant_journal` tool directly** — `quant_execute` does NOT have a `journal` action. Valid journal actions: `add`, `query`, `review`, `update` (NOT `record`).

## Decision Examples

### Example 1: Trending Regime, Bullish Cross-Asset
```
Phase 1: regime=trending, VIX=14, DXY falling, BTC leading SPX
Phase 2: "Strong risk-on environment. BTC momentum looks good. 
 SPY also trending. Confidence: 0.8"
Phase 3: Execute Strategy E (BTC buy, half position since already have BTC)
Phase 4: Risk check — portfolio now 8% exposed, within limits
Phase 5: Journal: "Bought BTC on trending regime + DXY weakness + BTC outperformance"
```

### Example 2: Ranging Regime, High IV, Holding SPY
```
Phase 1: regime=ranging, VIX=20, SPY flat for 2 weeks, IV rank=65
Phase 2: "Range-bound market with elevated IV. SPY covered call makes sense 
 — sell premium while waiting. Confidence: 0.75"
Phase 3: Execute Strategy B (sell SPY 3% OTM call, 30 DTE)
Phase 4: Risk check — covered call reduces risk, not increases
Phase 5: Journal: "Sold SPY covered call on ranging regime + high IV rank"
```

### Example 3: Crisis Regime, VIX Spike
```
Phase 1: regime=crisis, VIX=35, DXY surging, Gold up, SPX -3%
Phase 2: "Full risk-off. Must protect existing positions. Confidence: 0.9 
 for defense, 0.3 for offense → NO new positions, only hedges"
Phase 3: Execute Strategy C (buy protective puts on held stocks)
Phase 4: Risk check — puts increase protection, small cost
Phase 5: Journal: "Bought protective puts on crisis regime + VIX>30"
```

### Example 4: Low Confidence — NO TRADE
```
Phase 1: regime=neutral, mixed signals, VIX=18, DXY flat
Phase 2: "No clear edge. Conflicting signals. Confidence: 0.4"
Phase 3: SKIP — no trade
Phase 5: Journal: "No trade — low confidence (0.4), mixed signals, neutral regime"
```

### Example 5: Ranging Regime, Low IV — Also NO TRADE (2026-05-05 live)
```
Phase 1: regime=ranging, VIX=17.4, SPY IV rank=5.2, F&G=50 (rising from Fear)
Phase 2: "Ranging but IV too low for premium selling (covered call only pays 
 0.8% for 3% OTM 44DTE). BTC trending but maxed at 98.4% position. 
 Confidence: 0.45"
Action: Close decaying AAPL 270 put (-$139, -37% loss) to free position slot
Phase 3: NO TRADE — low IV makes income strategies unattractive
Phase 5: Journal: "No trade — ranging + low IV rank (5.2), closed AAPL put defensively"
```

### Example 6: Ranging + Low IV + BTC Maxed + No Edge (2026-05-06 live)
```
Phase 1: regime=ranging (ADX=14.29), VIX=17.07, SPY IV rank~0.2, F&G=46 (rising)
 BTC at 99% max position ($4,960/$5,000), SPY held with SL
 Gold +2.88% (hedging), DXY -0.42% (BTC supportive), Yields falling
Phase 2: "Ranging regime kills momentum. IV rank ~0.2 kills premium selling. 
 BTC maxed — can't add. One slot available but no strategy fits 
 regime+IV. Gold surge hints at hedging undercurrents. Confidence: 0.40"
Phase 3: NO TRADE — no strategy matches regime+IV+position constraints
Phase 4: Risk check — positions safe (BTC SL 3.6% away, SPY SL 3.3% away)
Phase 5: Journal #42: "No trade — ranging + IV rank 0.2 + BTC maxed + Gold hedging signal"
```

## Key Principles

1. **THINK FIRST, TRADE SECOND** — The LLM brain must always do Phase 2 before Phase 3
2. **TRADE LESS, THINK MORE** — 0-1 trades per session is optimal. No trade is a valid decision
3. **DEFENSE OVER OFFENSE** — When in doubt, protect existing positions, don't add new ones
4. **RESPECT THE REGIME** — Don't use momentum strategies in ranging markets, don't sell premium in crisis
5. **NEVER CHASE** — If you missed the entry, wait for the next signal. FOMO is the #1 enemy
6. **COST AWARENESS** — Every option has bid-ask spread. Every trade has fees. Small edges compound
7. **RATIO SPREAD = NAKED RISK** — Strategy I (ratio_spread) has unlimited loss on one short leg. Only use with confidence>=0.8 AND tight stop on underlying
8. **BUTTERFLY = NARROW ZONE** — Strategy G (iron butterfly) profits only if price pins near ATM. Use only when regime is strongly ranging
9. **CALENDAR = THETA GAME** — Strategy F (calendar_spread) profits from time decay differential. Works best in low-vol flat markets
10. **IV RANK, NOT JUST IV LEVEL** — Low IV rank (< 30) means premium selling is unattractive even if regime suggests it. Always check IV rank proxy from volatility action

## Pitfalls (learned from live execution)

- **option_close requires symbol/strike/expiry**, not just position id. Passing only `id` returns "symbol, strike, and expiry are required". Must pass: `action=option_close, symbol, option_type, strike, expiry`
- **quant_market_intel action=earnings has a bug** — returns `'dict' object has no attribute 'empty'` error for SPY. Don't rely on it; check earnings via news action instead
- **Covered call strategy analysis picks ATM + nearest expiry by default** — `quant_options strategy strategy_type=covered_call` defaults to 0DTE ATM which is useless. Always manually select expiry (30-45 DTE) and strike (3-5% OTM) based on chain data
- **Low IV rank (< 20) makes covered calls unattractive** — at IV rank proxy 5.2, SPY 3% OTM 44DTE call only pays ~0.8% premium. Not worth capping upside. Threshold: only sell covered calls when IV rank > 30
- **Closing OTM options early is valid defense** — if an option is far OTM with significant theta decay remaining, close it to: (1) stop premium bleed, (2) free position slot, (3) realize loss for record purposes. Better to take -37% now than -100% at expiry
- **Closing a position mid-session changes position_count** — after closing a position, position_count drops, opening a slot. Re-check status after any close before deciding on new trades
- **quant_indicators action=compute is NOT valid** — the correct action is `all` for full indicator computation. `compute` returns an error. Use individual actions (`sma`, `ema`, `rsi`, `macd`, `bollinger`, `atr`, `regime`, `all`)
- **quant_options action=expiries** — use this first to get valid expiry dates before calling chain. Passing wrong expiry format returns error
- **SPY volatility `current_atm_iv` field is broken** — returns 0.001 (unrealistic). Use `iv_rank_proxy` from the `surface` array entries instead. The `iv_rank_proxy` values (0-100 scale) are usable; the `current_atm_iv` is not
- **quant_indicators `all` action may return incomplete data for BTC** — SMA, EMA, RSI, ATR keys can be missing from `all` result. If key indicators are absent, call individual indicator actions (sma, ema, rsi, atr, macd, bollinger) separately for reliable data
- **quant_execute does NOT have a `journal` action** — journaling must use the `quant_journal` tool directly. Valid actions: `add`, `query`, `review`, `update` (NOT `record`)
- **Portfolio risk vs position value** — position VALUE ($8,579) ≠ actual RISK. True risk = sum of (entry - stop_loss) × amount for each position. Report both in Phase 4 risk check. A 9.3% position value might only be 0.3% actual risk to stop

## Notification Format (sent to Telegram after each run)
```
🧠 Strategy Brain Report
Regime: {composite_regime} | Risk: {risk_level}
VIX: {vix} | DXY: {dxy} | F&G: {fg_value}

Decision: {BUY/SELL/HOLD/NO_TRADE}
Strategy: {strategy_name}
Confidence: {confidence}/1.0
Reasoning: {2-3 sentence summary}

Portfolio: ${balance} | Risk: {risk_pct}% | Positions: {count}
```
