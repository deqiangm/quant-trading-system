---
name: quant-portfolio-status
version: 1.0
category: finance
description: "Quick status report across all Hermes quant trading accounts — cron jobs, portfolio positions, alpha scanner results, and crash warnings"
---

# Quant Portfolio Status Report

Quickly gather and present the status of all quant trading accounts running on Hermes cron jobs.

## Trigger
When the user asks about account status, portfolio status, trading status, or wants a summary of their trading positions.

## Data Source Map

All trading state is distributed — there is NO single file. Here's where to find each piece:

| Data | Location | How to Read |
|------|----------|-------------|
| Cron job list & status | `~/.hermes/cron/jobs.json` | Parse `jobs` array — each has `name`, `enabled`, `state`, `schedule_display`, `repeat.completed`, `last_run_at`, `last_status` |
| Cron output logs | `~/.hermes/cron/output/<job_id>/` | Job ID comes from jobs.json. Files are `YYYY-MM-DD_HH-MM-SS.md`. Latest file = latest run. |
| Alpha scanner reports | `~/.hermes/cron/alpha-stock-finder/reports/alpha_scan_v4_*.json` | Latest by filename sort. Keys: `top_picks` (list), `crash_warning`, `market_state_cn`, `total_scanned`, `alpha_candidates` |
| Crash warning standalone | `~/.hermes/cron/alpha-stock-finder/crash_warning_result.json` | 5-layer crash scoring |
| Paper trading DB | `~/.hermes/quant_trading/paper_trading.db` | SQLite DB — tables: balance, positions, orders, trade_results, daily_pnl, cooldown_state |
| Quant trading system files | `~/.hermes/cron/quant-trading-system/` | Backtest results, strategies, config |

## Step-by-Step Procedure

### Step 1: Get Cron Job Overview
```bash
python3 -c "
import json
with open('/home/deqiangm/.hermes/cron/jobs.json') as f:
    data = json.load(f)
for j in data.get('jobs', []):
    name = j.get('name','?')
    enabled = j.get('enabled', False)
    state = j.get('state','?')
    schedule = j.get('schedule_display','?')
    completed = j.get('repeat',{}).get('completed',0)
    last_run = j.get('last_run_at','?')
    last_status = j.get('last_status','?')
    job_id = j.get('id','?')
    print(f'{name}: {\"ACTIVE\" if enabled else \"PAUSED\"} | {schedule} | completed={completed} | last={last_status} @ {last_run} | id={job_id}')
"
```

### Step 2: Map Job IDs to Names
From jobs.json, note the `id` field for each trading-relevant job:
- Strategy Brain Trader → ID for portfolio data
- BTC Momentum Trader → ID for BTC positions
- Alpha Stock Scanner → ID for scanner results

### Step 3: Read Portfolio Status from DB (PREFERRED METHOD)

Direct DB query is more reliable than parsing cron output. Use this as the primary method.

```bash
# Write script to /tmp to avoid heredoc quoting issues
cat > /tmp/portfolio_check.py << 'EOF'
import sqlite3, os
db_path = os.path.expanduser("~/.hermes/quant_trading/paper_trading.db")
# Fallback: find ~/.hermes -name "paper_trading.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Balance
for r in conn.execute("SELECT * FROM balance").fetchall():
    print("Cash:", r["usd"], "| Initial:", r["initial_usd"])

# Positions — NOTE: for stocks, value = amount * price (contract_size is NOT used)
for r in conn.execute("SELECT * FROM positions").fetchall():
    print("Position:", r["symbol"], r["side"], r["amount"], "@", r["entry_price"],
          "| SL:", r["stop_loss_price"], "| Type:", r["instrument_type"],
          "| contract_size:", r["contract_size"])

# Daily PnL
for r in conn.execute("SELECT * FROM daily_pnl ORDER BY rowid DESC LIMIT 5").fetchall():
    print("P&L:", r["date"], r["realized_pnl"])

# Cooldown
for r in conn.execute("SELECT * FROM cooldown_state").fetchall():
    print("Cooldown:", r["cooldown_until"], "| Consecutive losses:", r["consecutive_losses"])
conn.close()
EOF
cd ~/.hermes/hermes-agent && source venv/bin/activate && python3 /tmp/portfolio_check.py
```

**Position value calculation rules:**
- Stock (instrument_type='stock'): value = amount × current_price
- Crypto (instrument_type='crypto'): value = amount × current_price
- Option (instrument_type='option'): value = amount × contract_size × premium
- **NEVER multiply stock/crypto amount by contract_size** — it defaults to 100 in the schema but only applies to options

### Step 3b: Read Portfolio Status from Strategy Brain Output (FALLBACK)
```bash
# Find latest output file for the strategy-brain job
ls -lt ~/.hermes/cron/output/<strategy_brain_id>/ | head -3

# Portfolio data is in the LAST ~60 lines of the output
tail -60 ~/.hermes/cron/output/<strategy_brain_id>/<latest_file>.md
```

Key data to extract:
- Total portfolio value (`Portfolio: $XX,XXX`)
- Risk percentage
- Position count and details (symbol, amount, entry, current, P&L, stop-loss)
- Strategy Brain decision (BUY/SELL/HOLD/NO_TRADE) and confidence

### Step 4: Read Latest Alpha Scanner Report
```bash
python3 -c "
import json
with open('<latest_report>.json') as f:
    d = json.load(f)
print('Time:', d.get('timestamp'))
print('Market:', d.get('market_state_cn'))
print('Scanned:', d.get('total_scanned'), '| Alpha:', d.get('alpha_candidates'))
cw = d.get('crash_warning', {})
print('Crash:', cw.get('warning_level'), '| Score:', cw.get('composite_score'))
top = d.get('top_picks', [])
for s in top[:8]:
    t = s.get('ticker','?')
    fs = s.get('fused_score','?')
    ts = s.get('technical_score','?')
    ss = s.get('social_signal','?')
    tv = s.get('tv_score','?')
    div = s.get('divergence_label','?')
    print(f'  {t:6s} Fusion:{fs:5.1f} | Tech:{ts:5.1f} | Social:{ss} | TV:{tv:5.1f} | Div:{div}')
"
```

### Step 5: Compile Report
Present in this format (Telegram-friendly, no markdown tables):

```
📊 量化交易系统状态汇报

🤖 Cron任务:
[active/paused status for each]

💰 组合状态:
总资产 / 初始资金 / PnL / 风险%

持仓明细:
- BTC/USDT: amount @ entry → current | P&L
- SPY: shares @ entry → current | P&L  
- Options: contract details | P&L

⚠️ 风险警告:
[any missing stop-losses, drawdowns, limit breaches]

📈 Alpha扫描:
[market state, top picks, crash warning]

🧠 Strategy Brain决策:
[latest decision and reasoning]
```

## Pitfalls

1. **DO NOT use `execute_code` for heavy JSON parsing** — it can timeout (300s limit). Use simple `python3 -c` one-liners via `terminal` instead.
2. **Terminal commands can get BLOCKED after timeout** — if a command times out, do NOT retry it. Use a different approach (e.g., simpler command).
3. **Cron output dirs are keyed by job ID hash** — not by name. Must cross-reference jobs.json first.
4. **Portfolio data is in cron OUTPUT logs** — not in a separate state file. The strategy-brain-trader writes its status report as the final output.
5. **Alpha scanner JSON keys**: stocks are under `top_picks` (NOT `candidates` or `alpha_candidates` for iterating picks). The full list is `all_candidates` (60 stocks), top subset is `top_picks` (20 stocks). Score field is `fused_score` (not `composite_score` or `fusion_score`). WARNING: the `alpha_candidates` field is a COUNT integer, NOT a list — iterating it returns 0 items every time. This caused all 135 reports to appear empty when accessed incorrectly.
6. **Latest scanner report**: sort by filename (includes timestamp). Don't rely on mtime alone.
7. **Some API calls may 429** — the scanner cron itself may fail with rate limits. Check `last_status` field and the actual output file content.
8. **Direct DB queries are more reliable than cron output logs** — for portfolio positions and balance, query `paper_trading.db` directly via sqlite3 instead of parsing cron output markdown. Tables: `balance`, `positions`, `orders`, `trade_results`, `cooldown_state`, `daily_pnl`. For live prices: `ccxt.okx().fetch_ticker('BTC/USDT')` for crypto, `yfinance.Ticker('SPY').fast_info['lastPrice']` for stocks.
9. **DB path is `~/.hermes/quant_trading/paper_trading.db`** — NOT `~/.hermes/cron/quant-trading-system/paper_trading.db`. Always use `find ~/.hermes -name "paper_trading.db"` if the path isn't found at the expected location.
10. **CRITICAL: contract_size=100 does NOT apply to stocks** — The DB schema has `contract_size` defaulting to 100 for ALL positions, but for stocks (instrument_type='stock'), the `amount` field is already in shares. Position value = amount × price (NOT amount × contract_size × price). Only options (instrument_type='option') use the contract_size multiplier. Blindly applying contract_size to stocks produces wildly inflated totals (e.g. $458K vs actual $100K). Check `instrument_type` before calculating position value.
11. **Avoid heredoc quoting issues with Python scripts** — When running Python via terminal with complex f-strings, write the script to /tmp/ first, then execute it. Inline heredocs with single/double quote mixing cause SyntaxError in Python's string parser.
