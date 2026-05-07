# Strategy Brain — LLM Global Reasoning Layer

The core decision engine that makes LLM a true "trading brain" instead of a rule-engine wrapper.

## Architecture

```
Market Intel (eyes) + Technical Indicators (ears) + Portfolio State (memory)
         ↓
   LLM Global Reasoning (brain) ← YOU ARE HERE
         ↓
   Strategy Selection → Tool Calls → Execution → Reflection
```

## Decision Framework

### Step 1: Situational Awareness (ALWAYS do this first)
```
1. quant_market_intel action=regime → Get composite regime
2. quant_market_intel action=sentiment symbol=<watchlist> → Sentiment scan
3. quant_market_intel action=macro → Cross-asset picture
4. quant_market_intel action=alpha_watchlist → Alpha V4 trade candidates (auto-rotating watchlist)
5. quant_execute action=status → Current portfolio state
```

### Step 2: LLM Reasoning (think before acting)
Based on Step 1 data, the LLM must answer these questions:

**Q1: What is the market regime?**
- crisis/stressed → DEFENSE mode (protect positions, raise cash)
- volatile_trend → CAUTIOUS mode (half positions, options for leverage)
- trending → ATTACK mode (full positions, momentum plays)
- ranging → INCOME mode (covered calls, mean reversion)
- contrarian_extreme_fear → OPPORTUNITY mode (scale in slowly)
- contrarian_extreme_greed → PROTECT mode (take profits, hedge)

**Q2: What does the cross-asset picture say?**
- DXY rising → pressure on BTC/commodities
- VIX > 25 → reduce equity exposure, buy protective puts
- Gold up + SPX down → risk-off rotation
- 10Y yield > 4.5% → pressure on growth/tech
- BTC leading SPX → risk appetite present

**Q3: What does sentiment say vs what price does?**
- Divergence = opportunity (bearish news but price rising = strong undercurrent)
- Agreement = confirmation (bearish news + falling price = real downtrend)

**Q4: What are my current positions and risk?**
- How much capital at risk? (never > 10% of portfolio)
- Am I over-concentrated in one direction?
- Do I have hedges in place?
- What's my daily P&L trajectory?

### Step 3: Strategy Selection Matrix

| Regime | Stock Strategy | Option Strategy | Position Size |
|--------|---------------|-----------------|---------------|
| crisis | Sell/raise cash | Long puts for hedge | 0-10% |
| stressed | Tighten stops | Protective puts | 10-20% |
| volatile_trend | Half-size momentum | Debit spreads | 30-40% |
| trending | Full momentum | Covered calls on winners | 50-70% |
| ranging | Mean reversion | Iron condors, credit spreads | 30-50% |
| contrarian_extreme_fear | Scale in slowly | Long ATM calls/puts | 20-40% |
| contrarian_extreme_greed | Take profits | Sell covered calls | Reduce to 30% |
| neutral | Balanced mix | Any (small size) | 30-50% |

### Step 3: Pre-Trade Checklist (MANDATORY before every execution)
1. ✅ Regime assessed? (not stale — within last 4h)
2. ✅ Risk budget available? (max 2% per trade, max 10% total)
3. ✅ Stop loss defined? (ATR-based for stocks, premium for options)
4. ✅ Correlation check? (not adding same-direction exposure)
5. ✅ News/event check? (no earnings in next 24h for stock trades)
6. ✅ VADER sentiment aligned? (not fighting strong sentiment unless contrarian signal)

### Step 4: Backtest Verification (MANDATORY for new strategies)
```
quant_backtest action=multi symbol=<target> strategy_type=<chosen_strategy> num_runs=6 holding_days=30
  → If win_rate < 40%: DO NOT trade this strategy on this symbol
  → If win_rate 40-60%: reduce position size to 50% of normal
  → If win_rate > 60%: proceed with normal sizing
  → Cross-reference: if avg_pnl < 0, the strategy has negative expectancy — skip
```

### Step 5: Execute
- For stocks: quant_execute action=buy/sell
- For options: quant_execute action=option_buy/option_sell
- Set stop: quant_execute action=set_stop_loss

### Step 6: Reflect (after each trade or at end of session)
```
quant_journal action=record → Log the decision reasoning
```
Key reflection questions:
- Did the regime assessment prove correct?
- Did sentiment alignment help or hurt?
- Was position sizing appropriate given outcome?
- What would I do differently?

## Stock Trading Workflows

### Momentum Buy (Trending Regime)
```
1. quant_market_intel action=regime symbol=<target> asset_class=stock
2. quant_market_intel action=news symbol=<target> limit=5
3. quant_indicators action=compute symbol=<target> asset_class=stock
   → Confirm: RSI < 70, MACD bullish crossover, price above SMA50
4. quant_execute action=buy symbol=<target> amount=<calculated> asset_class=stock
5. quant_execute action=set_stop_loss id=<pos_id> stop_price=<entry - 1.5*ATR>
```

### Protective Position (Stressed/Crisis)
```
1. quant_market_intel action=regime → confirms stressed/crisis
2. quant_execute action=status → identify unprotected long positions
3. quant_market_intel action=volatility symbol=<held_stock>
   → If IV LOW: buy protective puts (cheaper)
   → If IV HIGH: use collars (sell call + buy put)
4. quant_execute action=option_buy symbol=<held_stock> option_type=put
   strike=<5% OTM> expiry=<30-45 DTE>
5. quant_journal action=record → log hedge rationale
```

## Option Trading Workflows

### Covered Call (Ranging/Neutral, IV HIGH)
```
1. quant_market_intel action=regime → confirms ranging/neutral
2. quant_market_intel action=volatility symbol=<target>
   → IV > 30% = good covered call candidate
3. quant_execute action=status → confirm we hold the stock
4. quant_options action=strategy strategy_type=covered_call symbol=<target>
5. quant_execute action=option_sell symbol=<target> option_type=call
   strike=<3-5% OTM> expiry=<30 DTE>
```

### Iron Condor (Ranging, IV HIGH)
```
1. quant_market_intel action=regime → confirms ranging
2. quant_market_intel action=volatility symbol=SPY
   → IV > 20% = good for iron condor
3. quant_options action=strategy strategy_type=iron_condor symbol=SPY
4. Execute 4 legs:
   - option_sell put strike=<-2% OTM>
   - option_buy put strike=<-4% OTM>
   - option_sell call strike=<+2% OTM>
   - option_buy call strike=<+4% OTM>
   All same expiry (30-45 DTE)
```

### Earnings Play (Directional + Volatility)
```
1. quant_market_intel action=earnings symbol=<target>
2. quant_market_intel action=news symbol=<target> → assess direction
3. quant_market_intel action=volatility symbol=<target>
   → Pre-earnings IV usually inflated = SELL premium opportunity
4. If bullish expectation:
   - quant_execute action=option_buy call strike=ATM (if IV low)
   - OR quant_execute action=option_sell put strike=<5% OTM> (if IV high)
5. If neutral/volatility crush expected:
   - Iron condor or calendar spread
```

## Risk Management Rules (NON-NEGOTIABLE)

1. **Max 2% risk per trade** — position size = 2% of portfolio / (entry - stop)
2. **Max 10% total portfolio risk** — sum of all position risks
3. **Max 3 open positions** (stocks + options combined)
4. **Kill switch at 5% daily loss** — stop all trading for the day
5. **Cooldown: 4h after 3 consecutive losses**
6. **Never add to a losing position** (no averaging down)
7. **Option-specific**: 
   - Never sell naked options (always have protective long leg)
   - Max 2% of portfolio as option premium paid
   - Close options at 50% max loss or 21 DTE (whichever first)

## Watchlist

### Always Monitor
- BTC/USDT — crypto regime indicator
- SPY — equity regime indicator
- ^VIX — fear/volatility barometer
- DX-Y.NYB — dollar strength

### Alpha V4 Auto-Rotating Candidates (via alpha_watchlist)
Use `quant_market_intel action=alpha_watchlist` to get the latest Alpha scanner picks.
The scanner runs hourly and categorizes candidates into 5 strategy buckets:

| Category | Selection Criteria | Best Strategy | When to Use |
|----------|-------------------|---------------|-------------|
| momentum_long | tech>=60, social>=40, divergence<25 | Buy stock / ATM calls | Trending regime, bullish alignment |
| momentum_short | divergence>=35, social>>tech | Buy puts / bear spreads | Meme overhype, social divergence |
| premium_selling | social>=50, TV consensus buy/strong_buy | Covered calls / credit spreads | Ranging regime, high IV |
| premium_buying | tech>=50, social<30 | Debit spreads / long options | Low IV, under-hyped quality |
| divergence_plays | divergence>=25 | Contrarian entry | Tech/social disagreement |

### How to Use Alpha Watchlist in Strategy Selection
After running `alpha_watchlist` in Step 1:
1. Check crash_warning_level — if ELEVATED or CRASH, reduce all position sizes by 50%
2. Match regime to category: trending→momentum_long, ranging→premium_selling, volatile→divergence_plays
3. For each candidate, verify with `quant_indicators action=compute` before executing
4. Cross-reference with current portfolio — don't add same-direction exposure
5. Prioritize candidates with insider_signal=bullish or mention_spike_ratio>3x

## Pitfalls

- **Stale regime**: Regime can shift fast. If data > 4h old, re-assess before trading
- **VIX false signal**: VIX spikes can be 1-day events. Wait for 2-day confirmation
- **News lag**: yfinance news may be 15-60 min delayed. For breaking news, check cross-asset moves first
- **IV crush after earnings**: Never hold long options through earnings unless speculating
- **Correlation breakdown**: In crisis, all correlations go to 1. Don't assume diversification
- **Over-trading**: The LLM brain should TRADE LESS but THINK MORE. 0-2 trades per session is ideal
