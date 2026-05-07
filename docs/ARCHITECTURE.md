# 量化交易系统架构文档

## 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                     量化交易系统架构                              │
└─────────────────────────────────────────────────────────────────┘

                          ┌──────────────┐
                          │  Yahoo       │
                          │  Finance     │
                          │  (yfinance)  │
                          └──────┬───────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                        数据层 (Data Layer)                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ data_feed.py    │  │ alpha_signals/  │  │ AAPL_sample.csv │  │
│  │ 数据获取        │  │ 共享信号目录    │  │ 样本数据        │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                     策略层 (Strategy Layer)                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ SmaCross        │  │ EnhancedSmaCross│  │ RSIStrategy     │  │
│  │ SMA均线交叉     │  │ 增强版SMA       │  │ RSI超买超卖     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│  ┌─────────────────┐                                             │
│  │ MACDStrategy    │                                             │
│  │ MACD指标策略    │                                             │
│  └─────────────────┘                                             │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                     引擎层 (Engine Layer)                         │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    Backtrader Cerebro                        ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          ││
│  │  │ Broker      │  │ Analyzers   │  │ Observers   │          ││
│  │  │ 交易执行    │  │ 性能分析    │  │ 数据观察    │          ││
│  │  └─────────────┘  └─────────────┘  └─────────────┘          ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                     集成层 (Integration Layer)                    │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                  alpha_integration.py                        ││
│  │  ┌─────────────────────────────────────────────────────────┐││
│  │  │                  Alpha Scanner                            │││
│  │  │  /home/deqiangm/.hermes/cron/alpha-stock-finder/         │││
│  │  └─────────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                     输出层 (Output Layer)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ results/    │  │ logs/       │  │ reports/    │              │
│  │ 回测结果    │  │ 运行日志    │  │ 分析报告    │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 核心组件

### 1. Backtrader Cerebro (回测引擎)

**职责**:
- 加载策略和数据
- 执行回测循环
- 管理订单和持仓
- 收集分析结果

**配置**:
```python
cerebro = bt.Cerebro()
cerebro.broker.setcash(100000)      # 初始资金
cerebro.broker.setcommission(0.001) # 手续费率
cerebro.addsizer(bt.sizers.PercentSizer, percents=95)  # 仓位管理
```

### 2. Strategy 基类

**核心方法**:
- `__init__()`: 初始化指标和变量
- `next()`: 每个交易日执行的主逻辑
- `notify_order()`: 订单状态回调
- `notify_trade()`: 交易完成回调
- `stop()`: 策略结束回调

### 3. Analyzers (分析器)

| 分析器 | 功能 | 输出 |
|--------|------|------|
| SharpeRatio | 夏普比率 | 风险调整收益 |
| DrawDown | 回撤分析 | 最大回撤 |
| Returns | 收益分析 | 总收益率 |
| TradeAnalyzer | 交易统计 | 交易次数、胜率 |

---

## 数据流

### 1. 实时数据流

```
Yahoo Finance API
       │
       ▼
   yfinance.Ticker.history()
       │
       ▼
   DataFrame (OHLCV)
       │
       ▼
   bt.feeds.PandasData
       │
       ▼
   Strategy.next()
```

### 2. Alpha Scanner 数据流

```
Alpha Scanner (cron job)
       │
       ▼
   reports/alpha_scan_*.json
       │
       ▼
   alpha_integration.py
       │
       ▼
   data/alpha_signals/*.json
       │
       ▼
   scheduled_backtest.py
```

---

## 配置管理

### settings.yaml 结构

```yaml
# 数据源
data:
  source: yfinance
  default_symbol: AAPL
  default_start_date: "2024-01-01"
  default_end_date: "2024-12-31"

# 回测参数
backtest:
  initial_cash: 100000
  commission: 0.001
  slippage: 0.0

# 策略参数
strategies:
  sma_cross:
    fast_period: 10
    slow_period: 20

# 输出配置
output:
  log_dir: logs/
  results_dir: results/
  plot_enabled: true
```

---

## 扩展指南

### 添加新策略

1. **创建策略文件**:
```python
# strategies/my_strategy.py
import backtrader as bt

class MyStrategy(bt.Strategy):
    params = (('period', 20),)
    
    def __init__(self):
        self.sma = bt.indicators.SMA(self.data.close, period=self.params.period)
    
    def next(self):
        if self.sma > self.data.close:
            self.buy()
```

2. **在回测脚本中导入**:
```python
from strategies.my_strategy import MyStrategy
run_backtest(MyStrategy, symbol='AAPL')
```

### 添加新分析器

```python
cerebro.addanalyzer(bt.analyzers.Variance, _name='variance')
cerebro.addanalyzer(bt.analyzers.SQN, _name='sqn')  # 系统质量数
```

---

## 性能优化

### 1. 数据预加载

```python
# 预加载数据避免每次回测重新获取
data_cache = {}
for symbol in symbols:
    data_cache[symbol] = yf.Ticker(symbol).history(period='1y')
```

### 2. 批量回测

```python
# 使用 multiprocessing 并行回测
from multiprocessing import Pool

with Pool(processes=4) as pool:
    results = pool.map(run_backtest, strategy_symbol_pairs)
```

### 3. 缓存策略

- 数据缓存: 使用 `data/AAPL_sample.csv` 缓存常用数据
- 结果缓存: 历史回测结果保存在 `results/` 目录

---

## 监控与告警

### Cron Job 配置

定时回测可通过 Hermes Cron Job 配置:

```bash
# 每日定时回测
hermes cron add --schedule "0 9 * * *" -- python /path/to/scheduled_backtest.py
```

### 结果通知

回测完成后，结果自动:
1. 保存为 JSON 文件
2. 通过 Telegram 发送摘要
