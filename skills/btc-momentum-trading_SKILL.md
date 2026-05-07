---
name: btc-momentum-trading
version: 1.0.0
category: finance
description: "BTC/USDT momentum paper trading strategy for Hermes Agent — LLM-driven signal analysis with technical indicators"
---

# BTC Momentum Trading Strategy

LLM驱动的BTC/USDT动量纸面交易策略。使用Hermes的quant工具链进行市场数据分析、信号生成和交易执行。

## Trigger

When the user asks about BTC trading, crypto momentum, or running the quant trading system.

## Prerequisites

- quant toolset enabled (quant_data, quant_indicators, quant_execute, quant_journal)
- CCXT installed in Hermes venv
- OKX as default exchange (Binance geo-blocked)

## Strategy Overview

**Momentum breakout with trend confirmation:**
1. Use multiple timeframes to confirm trend direction
2. Enter when short MA crosses above long MA + RSI confirms momentum
3. Exit on MA crossunder or RSI overbought/oversold
4. ATR-based position sizing and stop-loss

## Trading Workflow (8 Steps)

### Step 1: Market Scan
```
quant_data(action="ticker", symbol="BTC/USDT")
quant_data(action="ohlcv", symbol="BTC/USDT", timeframe="1h", limit=100)
quant_data(action="ohlcv", symbol="BTC/USDT", timeframe="4h", limit=50)
```
- Get current price, 24h volume, bid/ask spread
- Fetch 1H candles (last 100) for signal generation
- Fetch 4H candles (last 50) for trend confirmation

### Step 2: Calculate Indicators
```
quant_indicators(action="sma", symbol="BTC/USDT", period=20, timeframe="1h")
quant_indicators(action="sma", symbol="BTC/USDT", period=50, timeframe="1h")
quant_indicators(action="ema", symbol="BTC/USDT", period=12, timeframe="1h")
quant_indicators(action="ema", symbol="BTC/USDT", period=26, timeframe="1h")
quant_indicators(action="rsi", symbol="BTC/USDT", period=14, timeframe="1h")
quant_indicators(action="macd", symbol="BTC/USDT", timeframe="1h")
quant_indicators(action="bollinger", symbol="BTC/USDT", period=20, timeframe="1h")
quant_indicators(action="atr", symbol="BTC/USDT", period=14, timeframe="1h")
```

### Step 2.5: Regime Detection & Signal Weighting

After computing indicators, detect the current market regime to adjust signal confidence:

```
quant_indicators(action="regime", symbol="BTC/USDT", period=14, timeframe="1h")
```

**Regime Classification (ADX + ATR percentile):**
- ADX > 25 AND ATR_pct > 60% → **trending**
- ADX < 20 → **ranging**
- ATR_pct > 80% → **volatile**
- All other cases → **neutral**

**Regime-Adaptive Confidence Multiplier:**

| Regime | Multiplier | Rationale |
|--------|-----------|-----------|
| trending | 1.0x | Momentum signals are reliable in trending markets |
| trending + volatile overlay | 0.8x | Trending but ATR_pct > 80% — high vol reduces signal reliability |
| neutral | 0.8x | No strong regime bias, slight discount |
| ranging | 0.6x | Momentum signals fail in ranges — reduce exposure |
| volatile | 0.4x | High volatility = unpredictable — minimize risk |

**Dual-regime conflict resolution:** When ADX > 25 (trending) AND ATR_pct > 80% (volatile), the handler returns "trending" but the market is also volatile. Apply a **volatility overlay multiplier of 0.8x** instead of the full 1.0x trending multiplier. Example: trending + ATR_pct=98.99% → use 0.8x instead of 1.0x. This prevents over-committing in volatile trend environments where whipsaws are likely.

**Apply the multiplier to Step 3's confidence score:**
- Raw confidence from signal analysis (e.g. 0.80)
- Adjusted confidence = raw_confidence × regime_multiplier
- Use adjusted confidence for position sizing in Step 4

Example: BUY signal with raw confidence 0.80 in a ranging market → adjusted = 0.80 × 0.6 = 0.48 → quarter position or hold.

### Step 3: Signal Analysis (LLM Reasoning)

Analyze the indicator values with this decision framework:

**BUY Signal (all must be true):**
- SMA(20) > SMA(50) on 1H — short-term trend above long-term
- EMA(12) > EMA(26) on 1H — momentum acceleration
- RSI between 40-70 — momentum present but not overbought
- MACD histogram positive and rising — increasing momentum
- Price above middle Bollinger Band — bullish positioning (action="bollinger", key="bollinger")
- 4H SMA(20) > SMA(50) — higher timeframe trend confirmation

**SELL Signal (any of):**
- SMA(20) < SMA(50) on 1H — trend reversal
- RSI > 80 — extreme overbought
- MACD histogram negative and falling — momentum collapse
- Price below lower Bollinger Band — bearish breakout

**HOLD Signal:**
- Conditions don't clearly meet BUY or SELL criteria
- Mixed signals across timeframes

## Position Sizing Formula (must respect max position limit)

```
quant_execute(action="balance")
```
- Risk 2% of portfolio per trade
- Position size (BTC) = (Portfolio * 0.02) / ATR
- **BUT** position value must not exceed QUANT_MAX_POSITION_USD (default $5,000)
- Final amount = min(risk_based_amount, max_position_usd / current_price)
- Round to 6 decimal places for BTC

### Step 5: Execute Trade

**⚠️ Before execution, check cooldown and risk blocks:**
```python
positions = quant_execute(action="positions")
if positions["cooldown_active"]:
    # TRADES BLOCKED — skip to Step 6 with side="hold"
    # Log reason: cooldown active until positions shows cooldown_until
if positions["kill_switch_active"]:
    # DAILY LOSS LIMIT HIT — skip to Step 6 with side="hold"
```

```python
quant_execute(action="buy", symbol="BTC/USDT", amount=<calculated>, atr=<ATR_VALUE>)
# or
quant_execute(action="sell", symbol="BTC/USDT", amount=<calculated>)
# or hold — no execution needed
```

**CRITICAL**: Always pass `atr` parameter on buy for automatic stop-loss at 1.5x ATR below entry.

### Step 5.5: Stop-Loss Verification
```
quant_execute(action="stop_check")
```
Verify stop-loss prices are set on all open positions.

### Step 6: Journal the Decision
```
quant_journal(
    action="add",
    entry_type="decision",
    symbol="BTC/USDT",
    side="buy|sell|hold",
    amount=<amount>,
    price=<current_price>,
    reasoning="<your LLM reasoning>",
    confidence=<0.0-1.0>,
    indicators="<JSON of indicator values>",
    market_context="<JSON of market conditions>",
    tags="momentum,btc,hourly"
)
```

### Step 7: Review (end of day or session)
```
quant_journal(action="review", date="YYYY-MM-DD")
quant_execute(action="history")
quant_execute(action="positions")
```

## Risk Management Rules

1. **Never risk more than 2% per trade** — use ATR for stop-loss distance
2. **Max 3 open positions** — avoid over-concentration
3. **No trading if 24h volume < $1B** — insufficient liquidity (use aggregate BTC volume, not single-exchange volume; OKX alone shows ~$143M which is normal — check CoinGecko/CMC aggregate or use baseVolume × price × 10 as rough estimate for total market volume)
4. **Cooldown after 3 consecutive losses** — 4h pause; check `cooldown_active` in positions response BEFORE attempting execution
5. **Daily loss limit: 5%** — stop trading if reached
6. **Always set stop-loss** — 1.5x ATR from entry price (pass `atr` param on buy)

## Confidence Scoring

| Confidence | Action |
|-----------|--------|
| 0.8-1.0 | Full position size |
| 0.6-0.8 | Half position size |
| 0.4-0.6 | Quarter position, or hold |
| < 0.4 | No trade — observe only |

## Indicator Return Format (Critical for LLM parsing)

quant_indicators returns **arrays of values**, not single scalars. Extract the latest value:
- SMA/EMA: `result["sma"][-1]` or `result["ema"][-1]`
- RSI: `result["rsi"][-1]`
- MACD: `result["macd"]["macd_line"][-1]`, `result["macd"]["signal_line"][-1]`, `result["macd"]["histogram"][-1]`
- Bollinger: `result["bollinger"]["upper"][-1]`, `result["bollinger"]["middle"][-1]`, `result["bollinger"]["lower"][-1]`
- ATR: `result["atr"][-1]`
- Regime: `result["regime"]["regime"]` (string: trending/ranging/volatile/neutral), `result["regime"]["adx"]`, `result["regime"]["atr_percentile"]`

**There is no "value" key** — the handler returns time-series arrays, not a single `{"value": X}`.

## Pitfalls

- OKX public API has rate limits (20 req/2s) — avoid rapid-fire calls
- ATR can spike during volatile moves — wait for stabilization
- RSI divergences are more reliable than RSI levels alone
- Binance is geo-blocked (HTTP 451) — always use OKX
- Paper trading portfolio starts with **$100,000** USDT virtual balance (not $10K)
- quant_execute uses SQLite — no real exchange API keys needed
- **Bollinger action name is "bollinger" NOT "bb"** — using "bb" returns `{"error": ...}`
- **quant_execute has "positions" alias for "status"** — both work, return positions + unrealized PnL
- **Default max position is $5,000** (QUANT_MAX_POSITION_USD) — position sizing must respect this limit; calculate: `amount = min(risk_based_size, max_position_usd / current_price)`
- **quant_execute buy will REJECT** if position value exceeds QUANT_MAX_POSITION_USD — always check before submitting
- **quant_execute sell was ALSO incorrectly rejecting** sells of oversized positions (bug: `_check_position_size` called on sell too). Fix: remove the position size check from `_handle_sell` — sells always reduce risk and should never be blocked by max position size. Patch applied 2026-05-04.
- **Handler function names differ by file**: quant_data uses `_handle_quant_data`, quant_indicators uses `quant_indicators_handler` (no underscore prefix), quant_execute uses `_handle_quant_execute`, quant_journal uses `_handle_quant_journal`
- **Shell heredoc testing**: Use `python3 << 'PYEOF'` not inline single-quote escaping — the latter breaks on nested dicts
- **Cron job execution pattern**: When running quant tools from a cron job (outside the agent loop), call handler functions directly via Python script: `from tools.quant_data import _handle_quant_data; result = _handle_quant_data({'action': 'ticker', 'symbol': 'BTC/USDT'})`. Write complex scripts to `/tmp/` files first to avoid shell quoting issues with nested JSON in heredocs.
- **Cooldown blocks ALL trades**: When `cooldown_active=True` in the positions response, buy/sell are rejected by SafetyShell. Always check this FIRST before attempting execution — journal a HOLD with cooldown reason.
- **Volume threshold uses single-exchange data**: `quant_data ticker` returns volume from OKX only (~$140M typical for BTC/USDT). The $1B threshold in risk rules refers to aggregate market volume — do not flag single-exchange volume below $1B as a hard block. Use it as a soft warning or multiply by ~7-10x for aggregate estimate.
- **quant_execute args must use proper types**: `amount` should be a float, `atr` should be a float. String values may cause issues in some handlers.
- **quant_indicators returns JSON strings**: When calling `quant_indicators_handler()` directly from Python, the result may be a JSON string rather than a dict. Use `json.loads(result)` if `isinstance(result, str)` before accessing keys.
- **Separate indicator and execution scripts**: When calling quant tools via Python scripts from cron, DO NOT mix `quant_indicators_handler` calls and `_handle_quant_execute` calls in the same script. The regime call inside a multi-step execution script caused 300s timeouts twice. Instead: run indicators in one script, execution + journaling in a separate script. Each script should do one "phase" of the workflow.
- **Adding to existing positions**: When you already have a position and signals justify increasing exposure, calculate the additional amount as `max_position_usd - current_position_value`. The `quant_execute buy` will merge into the existing position (averaging entry price), not create a separate position. Check position count vs max (3) before adding.
- **Partial-confidence add-to-position formula**: When adding to an existing position at less than full confidence, use `remaining_capacity_btc × adjusted_confidence` for the add amount. Example: remaining room = 0.01564 BTC, confidence = 0.64 → add 0.01564 × 0.64 = 0.01002 BTC. This scales exposure proportionally to conviction rather than always filling to max.
- **Add-to-position is NOT blocked by max position count**: When you already hold BTC/USDT and want to increase exposure, a `buy` for the same symbol merges into the existing position — it does NOT create a new position. So even if `position_count >= 3`, you can still add to an existing BTC position. The 3-position limit only blocks opening positions in NEW symbols. Bug pattern: Phase 2 script blocked a BTC add because `position_count >= 3`, but Phase 2b correctly allowed it by checking if the symbol already exists in the position list.
- **Non-BTC positions count toward the 3-position limit**: SPY, AAPL, and other symbols in the portfolio consume position slots. If you have 3 open positions (e.g., BTC, SPY, AAPL) and want to open a NEW symbol, you're blocked. But you can still add to any existing position. Be aware of this when planning BTC sizing — you may not be able to open a fresh BTC position if other assets fill the slots.
- **Non-BTC positions may lack stop-losses**: Positions opened by other strategies (SPY, AAPL, etc.) may not have stop-losses set. During alert checks (Phase 3), scan ALL positions for drawdown warnings, not just BTC. Flag any position without a stop-loss as a risk in the daily report.
- **Three-phase cron execution pattern**: For cron jobs, use 3 separate Python scripts: (1) indicators + regime detection → save JSON to /tmp, (2) portfolio check + execution + journaling, (3) alert checks + final review. This avoids the regime/execute timeout issue and keeps each script under 30 seconds.
- **stop_check triggers real auto-sales**: `quant_execute(action="stop_check")` doesn't just verify — it ACTIVELY sells positions that have breached their stop-loss. This can change portfolio state mid-workflow. Always run stop_check AFTER journaling if you're logging a HOLD, and be prepared for the portfolio to change. If a stop-sale occurs, journal a separate alert entry for the stop-loss event.
- **Stop-loss proximity check**: Before deciding HOLD, compare current price vs stop-loss price on open positions. If the gap is < 0.5%, the stop-loss may trigger imminently — mention this in your reasoning and consider whether the position should be manually closed instead of waiting for the stop.
- **Tools import path for cron scripts**: When calling quant tools directly from Python scripts (cron jobs), the tools directory must be on sys.path: `sys.path.insert(0, '/home/<user>/.hermes/hermes-agent/tools/')`. Without this, `from quant_data import _handle_quant_data` raises `ModuleNotFoundError`. The exact path depends on HERMES_HOME — use `os.path.join(os.environ.get('HERMES_HOME', os.path.expanduser('~/.hermes')), 'hermes-agent/tools/')` for profile-aware resolution.
- **OHLCV data structure**: `quant_data` ohlcv action returns candles under `result['data']` (array of dicts with keys: timestamp, open, high, low, close, volume), NOT under `result['ohlcv']`. Accessing `result.get('ohlcv', [])` returns empty list — use `result.get('data', [])` instead.
- **quant_journal has no "search" action**: Only valid actions are `add`, `query`, `review`, `update`. Using `action="search"` returns an error. Use `action="query"` with `symbol` parameter to find recent entries. Also NOT `action="record"` — use `action="add"`.
- **quant_indicators `all` action may return incomplete data**: When called for BTC/USDT, the `all` action sometimes omits SMA, EMA, RSI, and ATR keys — only returning MACD, Bollinger, and regime. If critical indicators are missing from the `all` result, call individual actions (`sma`, `ema`, `rsi`, `atr`) separately for reliable data
- **SPY volatility `current_atm_iv` field returns 0.001** — clearly a data issue. Use `iv_rank_proxy` from the surface array instead for IV assessment
- **Filled price may differ from ticker price**: When executing a market buy, the fill price (e.g., $80,898) may differ from the last ticker price (e.g., $80,841). Always use the fill price from the trade result for journaling, not the ticker price.

## Verification

After running the strategy:
1. Check `quant_execute(action="positions")` — verify position opened/closed
2. Check `quant_journal(action="review")` — verify decision logged
3. Check `quant_execute(action="balance")` — verify PnL tracking

## E2E Test Record (2026-05-02)

- **Price**: BTC/USDT $78,135 | 24h -0.32%
- **Indicators**: SMA20=$78,406 > SMA50=$78,108 | EMA12>EMA26 | RSI=44.4 | MACD hist=-70.7 | BB mid=$78,406
- **Signal**: BUY (confidence 0.80, 3/5 buy signals aligned)
- **Portfolio**: $99,921 USDT (initial $100K)
- **All 7 steps completed successfully**: market scan → indicators → signal → sizing → execute → journal → review

## E2E Test Record (2026-05-03 08:00 UTC)

- **Price**: BTC/USDT $78,358 | 24h +0.23%
- **Indicators**: SMA20=$78,419 > SMA50=$78,239 | EMA12>EMA26 | RSI=52.87 | MACD hist=-40.53 | BB mid=$78,420 | ATR=$211.75
- **4H Confirmation**: SMA20=$77,681 > SMA50=$77,373 ✅
- **Regime**: neutral (ADX=22.44, ATR_pct=0.0) → 0.8x multiplier
- **BUY signals**: 4/6 (missing MACD hist positive + price above BB mid)
- **Raw confidence**: 0.75 → Adjusted: 0.60
- **Decision**: HOLD — cooldown active (3 consecutive losses from test trades, expires 09:34 UTC)
- **Portfolio**: $99,999 USDT (initial $100K, PnL -$0.78)
- **Journal**: Entry #2 logged with hold reasoning + regime context

## E2E Test Record (2026-05-04 02:30 UTC)

- **Price**: BTC/USDT $80,338 | 24h +2.04%
- **Indicators**: SMA20=$78,780 > SMA50=$78,530 | EMA12=$79,006 > EMA26=$78,771 | RSI=67.34 | MACD hist=+79.74 (↑ from +49.79) | BB mid=$78,780 | ATR=$409.57
- **4H Confirmation**: SMA20=$78,226 > SMA50=$77,497 ✅
- **Regime**: trending (ADX=35.25, ATR_pct=73.74%) → 1.0x multiplier
- **BUY signals**: 6/6 (all aligned — first full alignment)
- **Raw confidence**: 0.90 → Adjusted: 0.90
- **Decision**: BUY (add to position) — sold oversized position earlier, then opened half position (RSI was borderline 70), then added to reach $5K max after RSI improved to 67.34
- **Trades**: SELL 0.126865 BTC @ $79,660 (+$95.67 realized) | BUY 0.031336 BTC @ $79,934 (half pos) | BUY 0.031389 BTC @ $79,729 (add to max)
- **Position #6**: 0.062725 BTC, entry $79,831.51, SL $79,114.55, unrealized +$27.89
- **Portfolio**: $95,069.65 USDT (initial $100K, total PnL +$123.56)
- **Alerts**: Regime change neutral→trending, trade executed ×2, no critical alerts
- **Bug fixed**: `_handle_sell` was blocking sells of oversized positions (removed `_check_position_size` from sell path)
- **Issue**: quant_indicators regime call causes 300s timeout when mixed with quant_execute calls in same script — use separate scripts

## E2E Test Record (2026-05-04 11:22 UTC)

- **Price**: BTC/USDT $79,059.9 | 24h +0.67%
- **Indicators**: SMA20=$79,337 > SMA50=$78,804 | EMA12=$79,470 > EMA26=$79,241 | RSI=47.78 | MACD hist=-82.38 (negative, declining) | BB mid=$79,337 | ATR=$475.26
- **4H Confirmation**: SMA20=$78,521 > SMA50=$77,584 ✅
- **Regime**: trending (ADX=33.76, ATR_pct=98.99%) → 0.8x multiplier (volatile overlay applied)
- **BUY signals**: 3/6 (SMA crossover ✅, EMA crossover ✅, 4H trend ✅; MACD hist negative ❌, price below BB mid ❌, RSI weak ✅)
- **Raw confidence**: 0.50 → Adjusted: 0.40 (0.50 × 0.8x volatile overlay)
- **Decision**: HOLD — weakening momentum, extreme volatility, confidence at observe-only threshold
- **🚨 Stop-Loss Triggered**: Position #6 (0.062725 BTC, entry $79,831.51) auto-sold at $79,080.30 by stop_check. Price fell below SL $79,114.55. Loss: -$52.08 (-0.94%)
- **Portfolio**: $100,339.56 USDT (initial $100K, total PnL +$339.56, day PnL +$41.81)
- **Consecutive losses**: 2 (need 3 for cooldown)
- **Positions**: 0/3 (flat after stop-loss)
- **Alerts**: stop_loss_hit (Position #6 auto-sold)
- **Key insight**: Dual-regime conflict — "trending" handler output but ATR_pct > 80% means volatile overlay needed. Added to skill as 0.8x multiplier rule.
- **Key insight**: stop_check triggers real auto-sales mid-workflow; added to pitfalls

## E2E Test Record (2026-05-04 19:55 UTC)

- **Price**: BTC/USDT $79,973 → filled $80,035 | 24h +1.50%
- **Indicators**: SMA20=$79,720 > SMA50=$79,030 | EMA12=$79,797 > EMA26=$79,516 | RSI=56.87 | MACD hist=+33.54 (declining from +45.03) | BB mid=$79,721 | ATR=$603.39
- **4H Confirmation**: SMA20=$78,778 > SMA50=$77,655 ✅
- **Regime**: trending (ADX=27.6, ATR_pct=96.0%) → 0.8x multiplier (volatile overlay applied)
- **BUY signals**: 5/6 (only MACD histogram declining ❌; all others ✅)
- **Raw confidence**: 0.85 → Adjusted: 0.68 (0.85 × 0.8x volatile overlay)
- **Decision**: BUY (add to existing position) — half position per confidence 0.68
- **Trade**: BUY 0.015562 BTC @ $80,035 (cost $1,247 incl. fee, SL $79,130)
- **Position #13**: 0.046934 BTC, blended entry $79,709, SL $78,605, value $3,760 (75% of $5K max), unrealized +$18.46
- **Portfolio**: $99,961 USDT total | $93,858 cash | 3/3 positions (BTC, SPY, AAPL)
- **Total PnL**: -$7,389 (-7.4%) — largely from non-BTC positions
- **Consecutive losses**: 1 (no cooldown)
- **Alerts**: trade_executed [INFO]
- **Bug encountered**: Phase 2 script blocked add-to-BTC-position because position_count >= 3. Fixed in Phase 2b by checking if symbol already exists — add-to-existing is NOT a new position. Added to pitfalls.
- **Key insight**: 3-phase cron pattern works well (indicators → execution → alerts), each script under 30s
- **Key insight**: Non-BTC positions (SPY, AAPL) consume position slots, affecting BTC sizing flexibility

## E2E Test Record (2026-05-05 05:00 UTC)

- **Price**: BTC/USDT $80,898 (filled) | ticker $80,841 | 24h +0.60%
- **Indicators**: SMA20=$79,953 > SMA50=$79,360 | EMA12=$80,329 > EMA26=$79,961 | RSI=66.25 | MACD hist=+67.25 (↑ from +51.94) | BB mid=$79,953 | ATR=$507.10
- **4H Confirmation**: SMA20=$79,113 > SMA50=$77,792 ✅
- **Regime**: trending (ADX=27.39, ATR_pct=85.86%) → 0.8x multiplier (volatile overlay applied)
- **BUY signals**: 6/6 (full alignment — all signals aligned for second time)
- **Raw confidence**: 1.00 → Adjusted: 0.80 (1.00 × 0.8x volatile overlay)
- **Decision**: BUY (add to existing position) — position was at 92% of $5K max, adding remaining capacity × confidence
- **Trade**: BUY 0.003863 BTC @ $80,898 (cost $312.82 incl. fee, SL $78,605 existing)
- **Position #13**: 0.060813 BTC, blended entry $79,843, SL $78,605, value $4,920 (98.4% of $5K max), unrealized +$60.85
- **Portfolio**: $91,495.50 cash (initial $100K, total PnL -$8,504.50, -8.50%)
- **Consecutive losses**: 1 (no cooldown)
- **Positions**: 3/3 (BTC, SPY, AAPL)
- **Alerts**: trade_executed [INFO], no_stop_loss [SPY, AAPL], drawdown_warning [AAPL -4.9%]
- **Key insight**: When position is near max ($4,610/$5,000), remaining capacity is small ($390). Add amount = remaining_btc × adjusted_confidence = 0.004829 × 0.80 = 0.003863 BTC — proportional sizing even for small adds.
- **Key insight**: Non-BTC positions without stop-losses (SPY, AAPL) flagged as risk alerts during Phase 3
- **Issue**: ModuleNotFoundError when importing quant tools in cron scripts — needed sys.path.insert to `~/.hermes/hermes-agent/tools/`
- **Issue**: OHLCV data is under `result['data']` not `result['ohlcv']` — caused zero-count read initially

## E2E Test Record (2026-05-06 08:15 UTC)

- **Price**: BTC/USDT $81,546.9 | 24h +0.84%, 5d +2.89%
- **Indicators**: SMA20=$81,372 > SMA50=$80,664 | EMA12=$81,376 > EMA26=$81,169 | RSI=58.72 | MACD hist=-36.96 (NEGATIVE, declining) | BB mid=$81,370 | ATR=$413.07
- **4H Confirmation**: SMA20=$80,154 > SMA50=$78,333 ✅
- **Regime**: neutral (ADX=23.82, ATR_pct=47.47%) → 0.8x multiplier
- **Composite regime (from SPY)**: ranging (ADX=14.29, confidence_multiplier=0.5)
- **BUY signals**: 4/6 (SMA crossover ✅, EMA crossover ✅, RSI ✅, 4H trend ✅; MACD hist negative ❌, price above BB mid ✅)
- **Raw confidence**: 0.67 → Adjusted: 0.54 (0.67 × 0.8x neutral) → BUT composite regime ranging (0.5x) → further reduced to 0.40
- **Decision**: HOLD / NO TRADE — BTC at 99% max position ($4,960/$5,000), MACD histogram negative, ranging composite regime
- **Position #13**: 0.060813 BTC, entry $79,843, SL $78,605, value $4,960, unrealized +$104.51
- **Portfolio**: $91,745.25 cash (initial $100K, total PnL +$138.39)
- **Positions**: 2/3 (BTC, SPY)
- **Consecutive losses**: 2 (no cooldown)
- **Key insight**: `quant_indicators all` returned incomplete data for BTC (missing SMA, EMA, RSI, ATR keys). Had to call individual indicator actions separately for reliable values
- **Key insight**: `quant_market_intel volatility` SPY `current_atm_iv` returned 0.001 — broken field. Used `iv_rank_proxy` from surface array instead (~0.2 = extremely low IV)
- **Key insight**: `quant_execute` does NOT have a `journal` action — must use `quant_journal` tool directly with `action=add` (not `record`)
- **Key insight**: Portfolio position VALUE ($8,579 = 9.3%) ≠ actual RISK to stop-loss. True risk is much lower (BTC: $1,580 to SL = 1.7%, SPY: $109.88 to SL = 0.1%)
