#!/usr/bin/env python3
"""
回测运行脚本
运行Backtrader回测示例
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtrader as bt
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# 导入策略
from strategies.sma_cross import SmaCross, RSIStrategy

def run_backtest(strategy_class, symbol='AAPL', 
                 start_date='2024-01-01', end_date='2024-12-31',
                 initial_cash=100000, commission=0.001):
    """
    运行回测
    
    Args:
        strategy_class: 策略类
        symbol: 股票代码
        start_date: 开始日期
        end_date: 结束日期
        initial_cash: 初始资金
        commission: 手续费率
    
    Returns:
        dict: 回测结果
    """
    print(f"\n{'='*60}")
    print(f"回测配置:")
    print(f"  策略: {strategy_class.__name__}")
    print(f"  标的: {symbol}")
    print(f"  时间: {start_date} 至 {end_date}")
    print(f"  初始资金: ${initial_cash:,.2f}")
    print(f"  手续费: {commission*100:.2f}%")
    print(f"{'='*60}\n")
    
    # 创建Cerebro引擎
    cerebro = bt.Cerebro()
    
    # 添加策略
    cerebro.addstrategy(strategy_class)
    
    # 获取数据
    print(f"正在获取 {symbol} 数据...")
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start_date, end=end_date)
    
    if df.empty:
        print(f"错误: 未能获取数据")
        return None
    
    # 标准化列名
    df.columns = [c.lower().replace(' ', '_') for c in df.columns]
    
    # 创建数据源
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)
    
    # 设置初始资金和手续费
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=commission)
    
    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    
    # 运行回测
    print("开始回测...\n")
    start_time = datetime.now()
    results = cerebro.run()
    end_time = datetime.now()
    
    strat = results[0]
    
    # 获取分析结果
    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    returns = strat.analyzers.returns.get_analysis()
    trades = strat.analyzers.trades.get_analysis()
    
    # 输出结果
    final_value = cerebro.broker.getvalue()
    pnl = final_value - initial_cash
    pnl_pct = (pnl / initial_cash) * 100
    
    print(f"\n{'='*60}")
    print(f"回测结果:")
    print(f"{'='*60}")
    print(f"  初始资金: ${initial_cash:,.2f}")
    print(f"  最终资金: ${final_value:,.2f}")
    print(f"  盈亏: ${pnl:,.2f} ({pnl_pct:+.2f}%)")
    print(f"  最大回撤: {drawdown.get('max', {}).get('drawdown', 0):.2f}%")
    
    # 夏普比率
    sharpe_ratio = sharpe.get('sharperatio')
    if sharpe_ratio is not None:
        print(f"  夏普比率: {sharpe_ratio:.4f}")
    else:
        print(f"  夏普比率: N/A (可能交易次数不足)")
    
    # 交易统计
    total_trades = trades.get('total', {}).get('total', 0)
    if total_trades > 0:
        won_trades = trades.get('won', {}).get('total', 0)
        lost_trades = trades.get('lost', {}).get('total', 0)
        win_rate = (won_trades / total_trades * 100) if total_trades > 0 else 0
        print(f"\n交易统计:")
        print(f"  总交易次数: {total_trades}")
        print(f"  盈利交易: {won_trades}")
        print(f"  亏损交易: {lost_trades}")
        print(f"  胜率: {win_rate:.1f}%")
    
    print(f"\n执行时间: {(end_time - start_time).total_seconds():.2f}秒")
    print(f"{'='*60}\n")
    
    return {
        'initial_cash': initial_cash,
        'final_value': final_value,
        'pnl': pnl,
        'pnl_pct': pnl_pct,
        'max_drawdown': drawdown.get('max', {}).get('drawdown', 0),
        'sharpe_ratio': sharpe_ratio,
        'total_trades': total_trades,
    }


def main():
    """主函数"""
    print("\n" + "="*60)
    print("Backtrader 回测验证")
    print("="*60)
    
    # 回测时间范围
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    
    # 运行SMA交叉策略
    print("\n### 测试1: SMA均线交叉策略 ###")
    result1 = run_backtest(
        SmaCross, 
        symbol='AAPL',
        start_date=start_date,
        end_date=end_date
    )
    
    # 运行RSI策略
    print("\n### 测试2: RSI策略 ###")
    result2 = run_backtest(
        RSIStrategy,
        symbol='AAPL',
        start_date=start_date,
        end_date=end_date
    )
    
    print("\n" + "="*60)
    print("所有回测验证完成 ✓")
    print("="*60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
