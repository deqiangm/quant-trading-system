---
name: alpha-stock-monitor
description: Create automated stock scanning systems with cron job scheduling for detecting breakout/momentum stocks
tags:
  - stocks
  - trading
  - cron
  - automation
  - technical-analysis
---

# Alpha Stock Monitor - Automated Stock Scanning System

Create and deploy an automated stock scanner that detects potential breakout/momentum stocks using technical analysis.

## Overview

This skill sets up a complete automated system that:
- Scans US stocks for breakout patterns and momentum signals
- Uses multi-factor scoring (52-week highs, volume, MACD, RSI, moving averages)
- Runs on a cron schedule (hourly by default)
- Generates and delivers formatted reports

## Key Components

### 1. Scanner Script (alpha_scanner.py)

Core scoring system with these factors:

| Signal | Score | Description |
|--------|-------|-------------|
| 52-week high breakout | +30 | Price near 52-week high |
| Volume surge 2x+ | +25 | Volume at least 2x average |
| 5-day gain >10% | +25 | Short-term momentum |
| 20-day gain >20% | +30 | Medium-term trend |
| MACD golden cross | +20 | Technical bullish signal |
| Moving avg alignment | +25 | SMA20 > SMA50 > SMA200 |
| RSI oversold bounce | +20 | Recovery from oversold |
| Bollinger breakout | +20 | Volatility expansion |

Minimum score threshold: 30 points to be included in candidates.

### 2. Data Source

Use **yfinance** (Yahoo Finance API) - free and reliable:
```bash
pip install yfinance pandas numpy pytz
```

### 3. Cron Job Setup

Use Hermes cronjob tool:
```python
cronjob(
    action="create",
    name="alpha-stock-scanner",
    prompt="Run scanner and send report...",
    schedule="every 1h",
    deliver="origin"  # Send to current conversation
)
```

### 4. Report Format Requirements

User requires:
- **Header**: Separator line + title + PST timestamp
- **Body**: Market sentiment (SPY/QQQ/IWM/DIA) + Top 20 candidates
- **Footer**: Completion timestamp in PST
- **No markdown** on Telegram (plain text with emojis)

Example format:
```
========================================
📈 Alpha Stock Scanner Report
========================================

⏰ 扫描时间: 2026-04-14 10:30:55 PM PST (Pacific Standard Time)

📊 Market Sentiment:
🟡 SPY: RSI 72.5 | 5D +5.3%
...

🔥 Top Alpha Picks:

1. WDC - Score: 160
 $366.22 | 5D: +17.4%
 Vol: 0.8x | RSI: 69
 🚀 [signals]

----------------------------------------
📤 报告生成完成: 2026-04-14 10:30:55 PM PST
----------------------------------------
```

### 5. PST Timestamp Code

```python
from datetime import datetime
import pytz

pst = pytz.timezone('America/Los_Angeles')
now_pst = datetime.now(pst)
time_str = now_pst.strftime('%Y-%m-%d %I:%M:%S %p PST (Pacific Standard Time)')
```

## Common Issues & Fixes

### Duplicate stocks in report
- Scanner may process same ticker multiple times
- Always deduplicate before generating report:
```python
seen = set()
unique = []
for s in results:
    if s['ticker'] not in seen:
        seen.add(s['ticker'])
        unique.append(s)
```

### top_picks count mismatch
- JSON report stores `top_picks` separately
- Update both the scanner AND the report generator to use same count (20)
- Scanner: `'top_picks': results[:20]`
- Report generator: `top_picks = unique_picks[:20]`

### KeyError: 'score' in generate_report.py with v4 JSON data
- **Root cause**: v3 scanner uses `score` field, v4 scanner uses `fused_score` field. `generate_report.py` hardcodes `stock['score']` which crashes on v4 JSON.
- **Fix**: Use `stock.get('fused_score', stock.get('score', 0))` as a fallback chain in BOTH the HTML report section AND the Telegram summary section of `generate_report.py`.
- **HTML report** (~line 183): Change `stock['score']` → `stock.get('fused_score', stock.get('score', 'N/A'))`
- **Telegram summary** (~line 277): Add `score = stock.get('fused_score', stock.get('score', 0))` before the f-string, then use `{score}` instead of `{stock['score']}`
- **Indentation pitfall**: When patching the Telegram summary line, ensure the replacement line uses exactly 8 spaces (matching the `for` loop body indentation). The patch tool may introduce inconsistent whitespace causing `IndentationError`. Verify with `py_compile` after editing.

### generate_report.py picks wrong (old) JSON file
- The script sorts `alpha_scan_*.json` by name and picks the first (newest). Both v3 files (`alpha_scan_YYYYMMDD_HHMM.json`) and v4 files (`alpha_scan_v4_YYYYMMDD_HHMM.json`) match this glob.
- If a v4 scan ran earlier but a v3 scan ran more recently, the script may pick the v3 file (correct behavior since it's newest). But if the v4 file has a later timestamp in the filename, it gets picked and then crashes on `score` key (see above).
- **The `score` fallback fix above resolves both cases** — v3 files have `score`, v4 files have `fused_score`, and the fallback chain handles both.

### Virtual environment activation
- Use full path to venv's python
- Or activate in shell script wrapper:
```bash
source /path/to/venv/bin/activate
python3 alpha_scanner.py
```

## File Structure

```
~/.hermes/cron/alpha-stock-finder/
├── alpha_scanner.py      # Main scanner script
├── generate_report.py    # Report generator
├── run_scan.sh           # Shell wrapper
├── config.yaml           # Configuration
├── logs/                 # Execution logs
├── reports/              # JSON reports + .summary files
└── html_reports/         # HTML visualization
```

## Stock Pool Selection

Include high-liquidity stocks across sectors:
- Tech giants: AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA
- Semiconductors: AMD, INTC, QCOM, AVGO, MU, AMAT, LRCX, KLAC
- Software/Cloud: CRM, ORCL, ADBE, NOW, SNOW, PLTR
- Fintech: V, MA, PYPL, SQ, COIN
- Current hot sectors (adjust based on market)

## Cron Job Management

```bash
# List jobs
hermes cron list

# Manual trigger
hermes cron run <job_id>

# Pause/Resume
hermes cron pause <job_id>
hermes cron resume <job_id>

# Update prompt
hermes cron update <job_id> --prompt "new instructions"
```

## AI Enhancement Features (v2.0)

Enhanced scanner (`alpha_scanner_enhanced.py`) adds machine learning concepts:

### 1. Dynamic Threshold System
- **RSI thresholds**: Adaptive based on historical distribution (10th/90th percentiles) instead of fixed 30/70
- **Volume anomaly**: Z-score based detection (>2.0 = high, >2.5 = extreme)
- **MACD strength**: Histogram momentum calculation

### 2. Trend Strength Quantification
- **Hurst Exponent**: Measures trend persistence (H>0.6 = strong trend)
- **ADX Enhancement**: ADX>25 = moderate trend, ADX>30 = strong trend
- **Bollinger Position**: 0-1 scale showing price position within bands

### 3. Signal Quality Scoring
Each signal has historical win rate weight:
- 52_week_high: 85% win rate
- Volume surge: 72% win rate
- MACD cross: 68% win rate
- MA alignment: 75% win rate

### 4. Market State Adaptation
- Detects bull/bear/sideways/volatile market states
- Adjusts signal weights based on market state
- Bull market: momentum signals weighted +10-20%
- Bear market: RSI bounce weighted +20%

### 5. Anomaly Detection (Isolation Forest concept)
- Volume Z-Score: Detects abnormal volume spikes
- Price Z-Score: Detects abnormal price movements
- Combined with technical signals for confirmation

### 6. Risk-Adjusted Scoring
- Volatility normalized returns
- ATR ratio used to adjust raw scores
- Higher volatility = lower base score multiplier

## V4 Scanner (alpha_scanner_v4.py) — Cron Job Workflow

### Running V4 from Cron

V4 scanner takes ~3-5 minutes (Reddit fetch + TV data + yfinance + LLM sentiment). Cron jobs MUST set `timeout=300` for the terminal call. If timeout is hit, the scanner may still have produced a partial report — check `reports/` directory.

```bash
source /home/deqiangm/.hermes/hermes-agent/venv/bin/activate
cd /home/deqiangm/.hermes/cron/alpha-stock-finder
python3 alpha_scanner_v4.py  # ~3-5 min, needs 300s timeout
```

### Timeout Handling

If scanner times out (exit code 124), check for existing today's report before retrying:
```bash
ls -lt /home/deqiangm/.hermes/cron/alpha-stock-finder/reports/alpha_scan_v4_*.json | head -3
```
Use the latest report from today if available — reports are typically generated every few hours via cron.

**Background process approach**: When running from a cron job, the 300s foreground timeout may not be enough. Use `terminal(background=true, notify_on_complete=true)` instead — the scanner can take up to ~12 minutes (730s observed). While waiting, read the latest existing report to prepare the summary. When the background process completes, read the new report file:
```python
# Start scanner in background
terminal(background=true, notify_on_complete=true, command="source /path/venv/bin/activate && cd /path && python3 alpha_scanner_v4.py")

# Meanwhile, read existing latest report and parse it
# When background completes, find the new report:
# ls -lt reports/alpha_scan_v4_*.json | head -1
```

### Parsing V4 JSON Reports

V4 JSON structure differs significantly from V3:
- **Top picks key**: `top_picks` (list of dicts with `fused_score`, not `score`)
- **Crash warning**: `crash_warning` object with `composite_score`, `warning_level`, `layers` dict
- **Market sentiment**: `market_sentiment` dict with SPY/QQQ/IWM/DIA sub-dicts
- **Social data**: `wsb_mentions`, `wsb_sentiment`, `cp_signal`, `social_conviction`, `mention_spike_ratio`
- **Divergence**: `divergence` (numeric) + `divergence_label` (aligned/moderate_divergence/high_divergence)

**DO NOT** try to parse JSON via `read_file()` + `json.loads()` in execute_code — the line-numbered format from `read_file` breaks JSON parsing. Also, `json.loads()` in execute_code with strict=True fails on Reddit-sourced text containing control characters (tabs, newlines inside strings). Instead:
1. Write a Python script to `/tmp/` using `write_file`
2. Run it with `terminal("python3 /tmp/script.py")` — Python's `json.load(f)` handles control chars correctly from file reads

**Cron timeout fallback**: When the scanner times out (exit code 124), don't immediately re-run — the V4 scanner may have already produced a report earlier today. Check `ls -lt reports/alpha_scan_v4_*.json | head -3` for a same-day report and use that instead. Re-running risks another timeout with no new data.

**V4 JSON field naming gotchas**:
- `alpha_candidates` is an **integer** (count), NOT a list of candidate objects. The full candidate list is in `all_candidates` (list of dicts).
- `top_picks` contains the ranked subset (typically top 20) with all scoring fields.
- When extracting top N for reports, use `top_picks` not `all_candidates` — it's pre-sorted by fused_score.

### V4 Report Key Fields for Summary

When generating cron report summaries, extract these sections:
1. **Market state**: `market_state`, `market_state_cn`, `market_sentiment` (ETF RSI/ADX/trend)
2. **Top 12 picks**: ticker, fused_score, technical_score, social_signal, tv_score, wsb_mentions+sentiment, divergence+label
3. **Crash warning 5-layer**: composite_score, warning_level, each layer's score+signals
4. **Social anomalies**: mention_spikes, cp_signal (call_bias/put_bias/heavy_calls/heavy_puts), high divergence stocks
5. **Insider data**: `insider_filings_found`, `insider_signals_count`

### Shell Quoting Pitfall in execute_code

When running Python one-liners via `terminal()` inside `execute_code()`, complex strings with `===` markers, Chinese characters, or inline JSON dicts frequently hit `SyntaxError: unterminated string literal` or `NameError` due to shell quoting layers. **Always use heredoc or write a `/tmp/` script file** — never try to inline multi-line Python with f-strings and special characters directly in a `terminal()` call string.

### V4 Notable Signal Fields

| Field | Meaning | Alert Threshold |
|-------|---------|-----------------|
| `cp_signal` = heavy_puts | Options market bearish | Contradicts social bullish |
| `cp_signal` = heavy_calls | Options market bullish | Confirms social bullish |
| `divergence_label` = high_divergence | Tech/social disagree strongly | >40 divergence value |
| `mention_spike_ratio` > 2.0 | Sudden Reddit attention | POET had 11.0x spike |
| `crash_warning.layers["Technical Extremes"].score` | Overbought/oversold risk | >30 = concerning |

## Customization Points

1. **Scoring weights**: Adjust in `analyze_enhanced_signals()`
2. **Stock pool**: Modify `CORE_TICKERS` list
3. **Threshold**: Change minimum score (enhanced: 25, classic: 30)
4. **Schedule**: Change cron frequency (currently 1h)
5. **Report count**: Change top_picks slice (currently 20)
6. **Signal weights**: Modify in `SignalQualityScorer` class
7. **Market adjustments**: Tune in `market_adjustments` dict
