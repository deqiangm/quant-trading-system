# 量化交易系统 🏗️

基于**Sandwich三层架构**（信息层→决策层→执行层）的综合量化交易系统，全部使用免费数据API，LLM增强智能。

## 架构

```
┌─────────────────────────────────────────────────┐
│                   信息层                          │
│  Alpha扫描器V4 · 市场情报 · 社交数据              │
│  yfinance · CCXT · Reddit · StockTwits · Finviz  │
│  TradingView · SEC Form4 · FRED · 恐惧贪婪指数    │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│                   决策层                          │
│  策略大脑 · LLM情绪分析 · 信号融合               │
│  SMA交叉 · 增强SMA · BTC动量                      │
│  均值回归 · 期权交易                              │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│                   执行层                          │
│  订单管理 · 风险控制 · 交易日志                    │
│  回测引擎 · 组合仪表盘                            │
│  双Telegram机器人告警                             │
└─────────────────────────────────────────────────┘
```

## 模块说明

### Alpha扫描器 (`alpha-scanner/`)
多维选股引擎V4.2，100+技术指标+机器学习评分。

| 文件 | 说明 |
|------|------|
| `alpha_scanner_v4.py` | 核心扫描引擎(V4) |
| `social_sentiment.py` | Reddit/StockTwits情绪分析 |
| `crash_warning.py` | 市场崩盘预警系统 |
| `tv_screener.py` | TradingView筛选器 |
| `insider_trading.py` | SEC Form4内部人交易监控 |
| `llm_sentiment.py` | DeepSeek V4 LLM情绪分析 |
| `generate_v4_report.py` | 双语报告生成器(中/英) |
| `dual_telegram_send.sh` | 双Bot Telegram发送 |
| `legacy/` | V1/V2/V3历史版本存档 |

### Hermes工具 (`hermes-tools/`)
8个Hermes Agent集成工具（共6,945行）。

| 工具 | 行数 | 说明 |
|------|------|------|
| `quant_data.py` | 508 | 行情数据获取(yfinance, CCXT) |
| `quant_market_intel.py` | 817 | 市场情报聚合 |
| `quant_indicators.py` | 563 | 技术指标计算 |
| `quant_execute.py` | 1,674 | 订单执行与风险管理 |
| `quant_options.py` | 1,156 | 期权链分析与交易 |
| `quant_journal.py` | 401 | 交易日志与盈亏追踪 |
| `quant_backtest.py` | 491 | 回测引擎 |
| `quant_dashboard.py` | 1,335 | 组合仪表盘与报告 |

## 数据源（全部免费）

| 来源 | 类型 | 覆盖范围 |
|------|------|----------|
| yfinance | 行情数据 | 美股、加密货币 |
| CCXT | 加密货币数据 | 100+交易所 |
| Reddit JSON API | 社交情绪 | r/wallstreetbets等 |
| StockTwits | 社交情绪 | 美股 |
| Finviz (BS4) | 基本面筛选 | 美股 |
| TradingView Screener | 技术筛选 | 全球市场 |
| SEC Form 4 RSS | 内部人交易 | 美股内部人 |
| FRED | 宏观经济 | 美国经济 |
| Alternative.me | 加密货币恐惧贪婪 | 加密市场 |
| CNN恐惧贪婪指数 | 市场情绪 | 美国市场 |
| DeepSeek V4 | LLM情绪 | 新闻分析 |

## Cron定时任务

| 任务 | 频率 | 说明 |
|------|------|------|
| Alpha扫描 | 每4小时 | 全市场扫描+报告 |
| 策略大脑 | 每4小时 | LLM驱动策略分析 |
| 崩盘预警 | 每2小时 | 市场崩盘监控 |
| BTC动量 | 每日 | BTC/USDT动量交易 |
| 均值回归 | 每日 | 多标的均值回归 |

## Telegram告警

报告通过`dual_telegram_send.sh`同时发送到**两个Bot**：
- **Bot1** (Ddong) → 个人告警
- **Bot2** (Iris) → 备用频道

## 许可证

MIT
