# 量化交易系统常见问题 (FAQ)

## 安装与环境

### Q1: 如何安装依赖？

```bash
# 激活虚拟环境
source /home/deqiangm/.hermes/hermes-agent/venv/bin/activate

# 安装依赖
uv pip install backtrader yfinance matplotlib
```

### Q2: Python 版本要求？

系统需要 Python 3.8 或更高版本。当前使用 Python 3.11.15。

### Q3: 依赖包版本？

| 包名 | 版本 | 用途 |
|------|------|------|
| backtrader | 1.9.78.123 | 回测框架 |
| yfinance | 0.2.2 | 数据获取 |
| matplotlib | 3.10.8 | 可视化 |

---

## 数据获取问题

### Q4: yfinance 获取数据失败？

**症状**: `HTTPError: Too Many Requests` 或 `ConnectionError`

**解决方案**:
1. 检查网络连接
2. 减少请求频率 (Yahoo Finance 有请求限制)
3. 使用已缓存的样本数据

### Q5: 数据列名不匹配？

**症状**: `KeyError: 'Close'` 或类似错误

**原因**: yfinance 新版本返回的列名格式变化

**解决方案**: 系统已自动处理
```python
df.columns = [c.lower().replace(' ', '_') for c in df.columns]
```

### Q6: 数据为空怎么办？

**可能原因**:
1. 股票代码错误
2. 市场休市日
3. 网络问题

**检查方法**:
```python
import yfinance as yf
ticker = yf.Ticker('AAPL')
df = ticker.history(period='1mo')
print(df.head())
```

---

## 回测问题

### Q7: 夏普比率为 None？

**原因**: 
- 交易次数不足
- 收益率波动过小或为0

**解决方案**:
- 使用更长的回测周期
- 选择波动性更大的标的
- 检查策略是否产生交易信号

### Q8: 回测速度慢？

**优化方法**:
1. 减少分析器数量
2. 关闭详细日志 (`printlog=False`)
3. 使用预加载的数据
4. 并行处理多个策略

### Q9: 订单被拒绝？

**可能原因**:
- 保证金不足
- 股票数量为0或负数
- 市场休市

**调试方法**:
```python
def notify_order(self, order):
    if order.status == order.Rejected:
        print(f'订单被拒绝: {order.info}')
```

---

## 策略问题

### Q10: 如何添加新策略？

1. 创建策略文件 `strategies/my_strategy.py`
2. 继承 `bt.Strategy`
3. 实现 `__init__` 和 `next` 方法
4. 在脚本中导入使用

**示例**:
```python
import backtrader as bt

class MyStrategy(bt.Strategy):
    def __init__(self):
        self.sma = bt.indicators.SMA(period=20)
    
    def next(self):
        if self.sma > self.data.close:
            self.buy()
```

### Q11: 策略参数如何传递？

使用 `params` 元组:
```python
class MyStrategy(bt.Strategy):
    params = (
        ('fast_period', 10),
        ('slow_period', 20),
    )
    
    def __init__(self):
        self.fast_sma = bt.indicators.SMA(period=self.params.fast_period)
```

### Q12: 如何设置止损止盈？

方法1: 使用订单类型
```python
# 止损单
self.sell(exectype=bt.Order.Stop, price=self.buyprice * 0.95)

# 止盈单
self.sell(exectype=bt.Order.Limit, price=self.buyprice * 1.15)
```

方法2: 在 next() 中判断
```python
if self.position:
    pnl_pct = (self.data.close[0] - self.buyprice) / self.buyprice
    if pnl_pct < -0.05:  # 止损
        self.sell()
    elif pnl_pct > 0.15:  # 止盈
        self.sell()
```

---

## Alpha Scanner 集成问题

### Q13: 找不到 Alpha Scanner 报告？

**检查路径**:
```python
from scripts.alpha_integration import AlphaScannerIntegration
integration = AlphaScannerIntegration()
report = integration.get_latest_report()
print(report)
```

**确保**:
- Alpha Scanner cron job 正在运行
- `reports/` 目录有 JSON 文件

### Q14: Alpha 候选为空？

**可能原因**:
- 市场没有符合评分标准的股票
- min_score 参数设置过高

**解决方案**:
```python
# 降低评分阈值
candidates = integration.get_alpha_candidates(min_score=30, max_count=10)
```

### Q15: 如何获取市场情绪？

```python
sentiment = integration.get_market_sentiment()
for symbol, data in sentiment.items():
    print(f"{symbol}: {data['trend']}, RSI: {data['rsi']}")
```

---

## 输出与结果问题

### Q16: 结果文件在哪里？

- 回测结果: `/home/deqiangm/.hermes/cron/quant-trading-system/results/`
- 日志文件: `/home/deqiangm/.hermes/cron/quant-trading-system/logs/`
- Alpha信号: `/home/deqiangm/.hermes/cron/quant-trading-system/data/alpha_signals/`

### Q17: 如何解读回测结果？

| 指标 | 含义 | 好的标准 |
|------|------|----------|
| 收益率 | 总盈亏比例 | 正值 |
| 夏普比率 | 风险调整收益 | >1 好, >2 优秀 |
| 最大回撤 | 最大亏损幅度 | <20% 可接受 |
| 胜率 | 盈利交易比例 | >50% |

### Q18: 如何可视化回测结果？

```python
# 添加绘图
cerebro.plot(style='candlestick')

# 或保存到文件
import matplotlib.pyplot as plt
fig = cerebro.plot(style='candlestick')[0][0]
fig.savefig('backtest_result.png')
```

---

## 性能与优化问题

### Q19: 回测内存占用高？

**优化方法**:
- 减少数据量 (缩短时间范围)
- 关闭不需要的分析器
- 及时清理大变量

### Q20: 如何加速批量回测？

使用多进程:
```python
from multiprocessing import Pool

def run_single(symbol):
    return run_backtest(SmaCross, symbol=symbol)

symbols = ['AAPL', 'MSFT', 'GOOGL']
with Pool(4) as pool:
    results = pool.map(run_single, symbols)
```

---

## 故障排除

### 错误: `ImportError: cannot import name 'SmaCross'`

**原因**: 模块路径问题

**解决**:
```python
import sys
sys.path.insert(0, '/home/deqiangm/.hermes/cron/quant-trading-system')
from strategies.sma_cross import SmaCross
```

### 错误: `ValueError: zero-size array to reduction operation`

**原因**: 数据不足计算指标

**解决**: 确保数据长度大于指标周期

### 错误: `AttributeError: 'NoneType' object has no attribute 'close'`

**原因**: 数据未正确加载

**解决**: 检查 yfinance 返回是否为空

---

## 联系支持

如遇到未列出的问题:
1. 查看 WORKLOG.md 中的历史问题解决记录
2. 查看 logs/ 目录的运行日志
3. 提交 issue 时请附带完整的错误信息和回测配置
