#!/usr/bin/env python3
"""
策略比较和回测脚本
运行多个策略并比较其表现
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtrader as bt
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import json

# 导入策略
from strategies.sma_cross import SmaCross, RSIStrategy
from strategies.enhanced_sma import EnhancedSmaCross, MACDStrategy

def run_strategy_comparison(symbols=['AAPL', 'MSFT', 'GOOGL'], 
                           start_date=None, 
                           end_date=None,
                           initial_cash=100000):
    """
    运行策略比较
    
    Args:
        symbols: 股票代码列表
        start_date: 开始日期
        end_date: 结束日期
        initial_cash: 初始资金
    
    Returns:
        dict: 所有策略和标的的回测结果
    """
    
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    
    strategies = [
        ('SMA Cross (10/20)', SmaCross),
        ('Enhanced SMA (10/30)', EnhancedSmaCross),
        ('RSI Strategy', RSIStrategy),
        ('MACD Strategy', MACDStrategy),
    ]
    
    all_results = []
    
    print("\n" + "="*80)
    print(f"量化策略回测比较报告")
    print(f"回测区间: {start_date} 至 {end_date}")
    print(f"初始资金: ${initial_cash:,.2f}")
    print("="*80)
    
    for symbol in symbols:
        print(f"\n{'='*80}")
        print(f"标的: {symbol}")
        print(f"{'='*80}")
        
        # 获取数据
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date, end=end_date)
            
            if df.empty:
                print(f"警告: 无法获取 {symbol} 数据，跳过...")
                continue
            
            # 标准化列名
            df.columns = [c.lower().replace(' ', '_') for c in df.columns]
            
            print(f"数据记录数: {len(df)}")
            print(f"日期范围: {df.index[0].strftime('%Y-%m-%d')} 至 {df.index[-1].strftime('%Y-%m-%d')}")
            
        except Exception as e:
            print(f"错误: 获取 {symbol} 数据失败 - {e}")
            continue
        
        for strategy_name, strategy_class in strategies:
            result = run_single_backtest(
                strategy_class=strategy_class,
                strategy_name=strategy_name,
                data=df,
                symbol=symbol,
                initial_cash=initial_cash
            )
            
            if result:
                all_results.append(result)
    
    # 生成汇总报告
    print("\n" + "="*80)
    print("策略表现汇总")
    print("="*80)
    
    if all_results:
        # 按收益率排序
        sorted_results = sorted(all_results, key=lambda x: x['pnl_pct'], reverse=True)
        
        print(f"\n{'策略':<25} {'标的':<8} {'收益率':>10} {'夏普比率':>10} {'最大回撤':>10} {'交易次数':>8}")
        print("-"*80)
        
        for r in sorted_results[:10]:  # 显示前10名
            sharpe_str = f"{r['sharpe_ratio']:.4f}" if r['sharpe_ratio'] else "N/A"
            print(f"{r['strategy']:<25} {r['symbol']:<8} {r['pnl_pct']:>+9.2f}% {sharpe_str:>10} {r['max_drawdown']:>9.2f}% {r['total_trades']:>8}")
    
    return all_results


def run_single_backtest(strategy_class, strategy_name, data, symbol, initial_cash=100000):
    """运行单个策略回测"""
    
    try:
        cerebro = bt.Cerebro()
        cerebro.addstrategy(strategy_class, printlog=False)  # 关闭详细日志
        
        # 添加数据
        data_feed = bt.feeds.PandasData(dataname=data)
        cerebro.adddata(data_feed)
        
        # 设置资金和手续费
        cerebro.broker.setcash(initial_cash)
        cerebro.broker.setcommission(commission=0.001)
        
        # 添加分析器
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        
        # 运行回测
        results = cerebro.run()
        strat = results[0]
        
        # 获取分析结果
        sharpe = strat.analyzers.sharpe.get_analysis()
        drawdown = strat.analyzers.drawdown.get_analysis()
        trades = strat.analyzers.trades.get_analysis()
        
        final_value = cerebro.broker.getvalue()
        pnl = final_value - initial_cash
        pnl_pct = (pnl / initial_cash) * 100
        
        total_trades = trades.get('total', {}).get('total', 0)
        max_drawdown = drawdown.get('max', {}).get('drawdown', 0)
        sharpe_ratio = sharpe.get('sharperatio')
        
        print(f"\n{strategy_name}:")
        print(f"  最终资金: ${final_value:,.2f}")
        print(f"  收益率: {pnl_pct:+.2f}%")
        print(f"  夏普比率: {sharpe_ratio:.4f}" if sharpe_ratio else "  夏普比率: N/A")
        print(f"  最大回撤: {max_drawdown:.2f}%")
        print(f"  交易次数: {total_trades}")
        
        return {
            'strategy': strategy_name,
            'symbol': symbol,
            'initial_cash': initial_cash,
            'final_value': final_value,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'total_trades': total_trades,
        }
        
    except Exception as e:
        print(f"  错误: {strategy_name} 回测失败 - {e}")
        return None


def main():
    """主函数"""
    print("\n" + "="*80)
    print("量化交易系统 - 策略比较测试")
    print("="*80)
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 运行策略比较
    results = run_strategy_comparison(
        symbols=['AAPL', 'MSFT', 'SPY'],  # 测试股票和指数ETF
        initial_cash=100000
    )
    
    # 保存结果到JSON
    if results:
        results_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'results')
        os.makedirs(results_dir, exist_ok=True)
        
        output_file = os.path.join(results_dir, f'backtest_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n结果已保存至: {output_file}")
    
    print("\n" + "="*80)
    print("策略比较测试完成 ✓")
    print("="*80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
