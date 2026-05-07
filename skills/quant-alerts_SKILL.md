---
name: quant-alerts
version: 1.0.0
description: Quant trading alert system — Telegram notifications for trades, stop-losses, regime changes, and risk events
category: finance
---

# Quant Trading Alert System

## Overview

Sends Telegram notifications when key trading events occur. Designed to be called by the trading cron job or manually.

## Alert Types

| Alert | Trigger | Priority |
|-------|---------|----------|
| trade_executed | Buy/sell filled | INFO |
| stop_loss_hit | Stop-loss auto-sold | CRITICAL |
| regime_change | Market regime shifts (trending↔ranging↔volatile) | WARNING |
| kill_switch | Daily loss > 5%, trading halted | CRITICAL |
| cooldown_start | 3 consecutive losses, 4h cooldown | WARNING |
| drawdown_warning | Unrealized loss > 3% on any position | WARNING |
| daily_summary | End-of-day portfolio report | INFO |
| backtest_alert | Walk-forward overfitting risk HIGH or resilience < 0.3 | WARNING |

## Workflow

### Step 1: Check Portfolio State
```
quant_execute(action="status")
quant_execute(action="positions")
quant_indicators(action="regime", symbol="BTC/USDT", timeframe="1h")
```

### Step 2: Detect Alert Conditions
Compare current state vs last known state (stored in journal or memory):
- New trade executed? → trade_executed
- Any position breached stop-loss? → stop_loss_hit
- Regime changed from last check? → regime_change
- Kill switch active? → kill_switch
- Cooldown active? → cooldown_start
- Any position unrealized loss > 3%? → drawdown_warning

### Step 3: Format Alert Message

Format based on alert type:

**trade_executed:**
```
📊 TRADE: {side.upper()} {amount} {symbol} @ ${price:,.1f}
Stop-loss: ${stop_loss:,.1f} | Confidence: {confidence}
Portfolio: ${portfolio_value:,.0f} USDT
```

**stop_loss_hit:**
```
🚨 STOP-LOSS TRIGGERED: {symbol}
Entry: ${entry:,.1f} → Exit: ${exit:,.1f}
Loss: {loss_pct:.1f}% | ${loss_amount:,.0f}
Portfolio: ${portfolio_value:,.0f} USDT
```

**regime_change:**
```
🔄 REGIME CHANGE: {symbol}
{old_regime} → {new_regime}
ADX: {adx:.1f} | ATR%: {atr_pct:.0f}%
Confidence multiplier: {old_mult}x → {new_mult}x
```

**kill_switch:**
```
⛔ KILL SWITCH ACTIVATED
Daily loss: ${daily_loss:,.0f} ({daily_loss_pct:.1f}%)
All trading halted for remainder of day.
```

**cooldown_start:**
```
⏸️ COOLDOWN: 4h trading pause
Reason: 3 consecutive losing trades
Resume: {resume_time}
```

**drawdown_warning:**
```
⚠️ DRAWDOWN WARNING: {symbol}
Entry: ${entry:,.1f} → Current: ${current:,.1f}
Unrealized loss: {loss_pct:.1f}% (${loss_amount:,.0f})
Stop-loss at: ${stop_loss:,.1f}
```

**daily_summary:**
```
📈 DAILY REPORT
Portfolio: ${portfolio_value:,.0f} USDT
Day PnL: ${pnl:,.0f} ({pnl_pct:.1f}%)
Positions: {count}/{max}
Trades today: {trades}
Kill switch: {active/inactive} | Cooldown: {active/inactive}
```

**backtest_alert:**
```
🔬 BACKTEST WARNING: {strategy} {symbol}
Overfitting risk: {risk} (degradation: {deg_pct:.0f}%)
Avg resilience: {resilience:.2f}
Consider: {recommendation}
```

### Step 4: Send Notification
Use text_to_speech or direct message delivery (Hermes auto-delivers to the current chat).
For critical alerts (stop_loss_hit, kill_switch), also consider text_to_speech for audio notification.

### Step 5: Log Alert
```
quant_journal(action="add", entry_type="alert", symbol="...",
              reasoning="alert details", tags="alert,{alert_type}")
```

## Integration with Cron

Add to the btc-momentum-trader cron prompt:
```
After trading, run alert checks:
1. Compare current regime vs last logged regime
2. Check stop_check results
3. If any alert triggered, format and include in your response
4. The response auto-delivers to Telegram
```

## Configuration

Alert thresholds can be configured via environment variables:
- QUANT_ALERT_DRAWDOWN_PCT: Drawdown warning threshold (default 3%)
- QUANT_ALERT_COOLDOWN_LOSSES: Consecutive losses for cooldown (default 3)
- QUANT_ALERT_KILL_SWITCH_PCT: Daily loss kill switch (default 5%)

## Three-Validation Check

1. **First Principles**: Alerts must be triggered by objective, measurable conditions — not subjective assessments. Each alert has a clear threshold.
2. **Induction**: Alert patterns from real trading sessions should be reviewed monthly to adjust thresholds. A 3% drawdown in BTC is different from 3% in a stablecoin.
3. **Deduction**: If the system correctly detects all alert conditions in paper trading, it will detect them in live trading — the logic is identical.
