# Quant Trading System 🏗️

A comprehensive quantitative trading system built on the **Sandwich 3-Layer Architecture** (Information → Decision → Execution), powered by free data APIs and LLM-enhanced intelligence.

## Architecture

```
┌─────────────────────────────────────────────────┐
│              Information Layer                    │
│  Alpha Scanner V4 · Market Intel · Social Data   │
│  yfinance · CCXT · Reddit · StockTwits · Finviz  │
│  TradingView · SEC Form4 · FRED · Fear&Greed     │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              Decision Layer                       │
│  Strategy Brain · LLM Sentiment · Signal Fusion  │
│  SMA Cross · Enhanced SMA · BTC Momentum          │
│  Mean Reversion · Options Trader                  │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              Execution Layer                      │
│  Order Management · Risk Control · Journal        │
│  Backtest Engine · Portfolio Dashboard            │
│  Dual Telegram Alerts (Bot1 + Bot2)              │
└─────────────────────────────────────────────────┘
```

## Modules

### Alpha Scanner (`alpha-scanner/`)
Multi-dimension stock scanning engine V4.2 with 100+ technical indicators and ML scoring.

| File | Description |
|------|-------------|
| `alpha_scanner_v4.py` | Core scanner engine (V4) |
| `social_sentiment.py` | Reddit/StockTwits sentiment analysis |
| `crash_warning.py` | Market crash early warning system |
| `tv_screener.py` | TradingView screener integration |
| `insider_trading.py` | SEC Form 4 insider trading monitor |
| `llm_sentiment.py` | DeepSeek V4 LLM-powered sentiment analysis |
| `generate_v4_report.py` | Bilingual report generator (CN/EN) |
| `dual_telegram_send.sh` | Dual bot Telegram delivery |
| `run_scan.sh` | Cron entry point script |
| `config.yaml` | Scanner configuration |
| `legacy/` | V1/V2/V3 archived versions |

### Hermes Tools (`hermes-tools/`)
8 integrated tools for the Hermes Agent platform (6,945 lines total).

| Tool | Lines | Description |
|------|-------|-------------|
| `quant_data.py` | 508 | Market data fetcher (yfinance, CCXT) |
| `quant_market_intel.py` | 817 | Market intelligence aggregator |
| `quant_indicators.py` | 563 | Technical indicator calculator |
| `quant_execute.py` | 1,674 | Order execution & risk management |
| `quant_options.py` | 1,156 | Options chain analysis & trading |
| `quant_journal.py` | 401 | Trading journal & P&L tracking |
| `quant_backtest.py` | 491 | Backtesting engine |
| `quant_dashboard.py` | 1,335 | Portfolio dashboard & reporting |

### Strategies (`strategies/`)
| File | Description |
|------|-------------|
| `sma_cross.py` | Simple moving average crossover |
| `enhanced_sma.py` | Enhanced SMA with volume confirmation |

### Scripts (`scripts/`)
| File | Description |
|------|-------------|
| `alpha_integration.py` | Alpha scanner integration bridge |
| `data_feed.py` | Real-time data feed manager |
| `run_backtest.py` | Backtest runner |
| `scheduled_backtest.py` | Scheduled backtest execution |
| `strategy_comparison.py` | Multi-strategy comparison framework |

### Skills (`skills/`)
Hermes Agent skill definitions for each trading module.

## Data Sources (All Free)

| Source | Type | Coverage |
|--------|------|----------|
| yfinance | Market data | US stocks, crypto |
| CCXT | Crypto data | 100+ exchanges |
| Reddit JSON API | Social sentiment | r/wallstreetbets etc. |
| StockTwits | Social sentiment | US stocks |
| Finviz (BS4) | Fundamental screen | US stocks |
| TradingView Screener | Technical screen | Global markets |
| SEC Form 4 RSS | Insider trading | US insiders |
| FRED | Macro economics | US economy |
| Alternative.me | Crypto fear & greed | Crypto market |
| CNN Fear & Greed | Market sentiment | US market |
| DeepSeek V4 (NVIDIA free tier) | LLM sentiment | News analysis |
| VADER NLP | Text sentiment | Social media |

## Cron Jobs

The system runs on automated schedules via Hermes Agent:

| Job | Schedule | Description |
|-----|----------|-------------|
| Alpha Scanner | Every 4h | Full market scan + report |
| Strategy Brain | Every 4h | LLM-driven strategy analysis |
| Crash Warning | Every 2h | Market crash monitoring |
| BTC Momentum | Daily | BTC/USDT momentum trading |
| Mean Reversion | Daily | Multi-symbol mean reversion |

## Telegram Alerts

Reports are delivered to **two bots simultaneously** via `dual_telegram_send.sh`:
- **Bot1** (Ddong) → Personal alerts
- **Bot2** (Iris) → Secondary channel

## Setup

```bash
# Alpha Scanner
cd alpha-scanner
pip install yfinance ccxt beautifulsoup4 vaderSentiment requests
python alpha_scanner_v4.py

# Backtest
cd ../scripts
python run_backtest.py --strategy sma_cross --symbol SPY

# Hermes Tools
# Copy hermes-tools/*.py to your hermes-agent/tools/ directory
```

## Project Status

- [x] Information Layer — Alpha Scanner V4.2 operational
- [x] Decision Layer — Strategy Brain + LLM sentiment
- [x] Execution Layer — Paper trading active
- [x] Dual Telegram alerts
- [x] Automated cron scheduling
- [ ] Live trading integration
- [ ] Risk management hardening

## License

MIT
