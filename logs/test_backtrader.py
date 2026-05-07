import backtrader as bt
import yfinance as yf
import pandas as pd
from datetime import datetime

# 定义简单的均线交叉策略
class SmaCross(bt.Strategy):
    params = (('sma1', 10), ('sma2', 20))
    
    def __init__(self):
        self.sma1 = bt.indicators.SMA(self.data.close, period=self.p.sma1)
        self.sma2 = bt.indicators.SMA(self.data.close, period=self.p.sma2)
        self.crossover = bt.indicators.CrossOver(self.sma1, self.sma2)
    
    def next(self):
        if not self.position:
            if self.crossover > 0:
                self.buy()
        else:
            if self.crossover < 0:
                self.close()

# 创建回测引擎
cerebro = bt.Cerebro()
cerebro.addstrategy(SmaCross)

# 使用yfinance获取数据
print("正在从Yahoo Finance获取AAPL数据...")
data = yf.download('AAPL', start='2024-01-01', end='2024-12-31', progress=False)

# 处理MultiIndex列名问题 (yfinance新版本返回多级列名)
if isinstance(data.columns, pd.MultiIndex):
    data.columns = data.columns.get_level_values(0)

# 确保列名小写
data.columns = [c.lower() for c in data.columns]

# 转换为Backtrader数据格式
feed = bt.feeds.PandasData(dataname=data)
cerebro.adddata(feed)

# 设置初始资金
cerebro.broker.setcash(100000)

# 添加分析器
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')

print(f"初始资金: ${cerebro.broker.getvalue():,.2f}")

# 运行回测
results = cerebro.run()
strat = results[0]

print(f"最终资金: ${cerebro.broker.getvalue():,.2f}")

# 输出分析结果
sharpe = strat.analyzers.sharpe.get_analysis()
drawdown = strat.analyzers.drawdown.get_analysis()
returns = strat.analyzers.returns.get_analysis()

print("\n=== 回测分析结果 ===")
print(f"夏普比率: {sharpe.get('sharperatio', 'N/A')}")
print(f"最大回撤: {drawdown.get('max', {}).get('drawdown', 'N/A')}%")
print(f"年化收益率: {returns.get('rnorm100', 'N/A')}%")
print("\n=== Backtrader验证成功 ===")
