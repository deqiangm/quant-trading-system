#!/usr/bin/env python3
"""
定时回测脚本
用于 Cron Job 定时执行回测并生成报告
"""

import sys
import os
import json
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import backtrader as bt
import yfinance as yf
import pandas as pd

# 导入策略
from strategies.sma_cross import SmaCross, RSIStrategy
from strategies.enhanced_sma import EnhancedSmaCross, MACDStrategy

# 导入 Alpha 集成
from scripts.alpha_integration import AlphaScannerIntegration


def run_backtest_for_ticker(strategy_class, symbol, start_date, end_date, 
                            initial_cash=100000, commission=0.001):
    """
    运行单个标的的回测
    """
    try:
        # 获取数据
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date)
        
        if df.empty:
            return None
        
        # 标准化列名
        df.columns = [c.lower().replace(' ', '_') for c in df.columns]
        
        # 创建回测引擎
        cerebro = bt.Cerebro()
        cerebro.addstrategy(strategy_class, printlog=False)
        cerebro.adddata(bt.feeds.PandasData(dataname=df))
        cerebro.broker.setcash(initial_cash)
        cerebro.broker.setcommission(commission=commission)
        
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
        
        return {
            'symbol': symbol,
            'strategy': strategy_class.__name__,
            'initial_cash': initial_cash,
            'final_value': final_value,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'sharpe_ratio': sharpe.get('sharperatio'),
            'max_drawdown': drawdown.get('max', {}).get('drawdown', 0),
            'total_trades': trades.get('total', {}).get('total', 0),
            'status': 'success'
        }
        
    except Exception as e:
        return {
            'symbol': symbol,
            'strategy': strategy_class.__name__,
            'error': str(e),
            'status': 'error'
        }


def run_scheduled_backtest():
    """
    运行定时回测任务
    
    流程:
    1. 从 Alpha Scanner 获取最新候选
    2. 为每个候选运行策略回测
    3. 生成汇总报告
    """
    print("\n" + "="*60)
    print("量化交易系统 - 定时回测")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # 回测参数
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    
    # 策略列表
    strategies = [
        ('SMA Cross', SmaCross),
        ('Enhanced SMA', EnhancedSmaCross),
        ('RSI', RSIStrategy),
        ('MACD', MACDStrategy),
    ]
    
    # 获取 Alpha Scanner 候选
    integration = AlphaScannerIntegration()
    alpha_candidates = integration.get_alpha_candidates(min_score=80, max_count=5)
    
    # 获取关注列表 (如果 Alpha Scanner 没有候选)
    if not alpha_candidates:
        # 使用默认关注列表
        watch_list = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA']
        alpha_candidates = [{'ticker': t, 'score': 0} for t in watch_list[:5]]
    
    tickers = [c['ticker'] for c in alpha_candidates]
    print(f"\n回测标的: {', '.join(tickers)}")
    
    # 运行回测
    all_results = []
    
    for ticker in tickers:
        print(f"\n--- {ticker} ---")
        
        for strategy_name, strategy_class in strategies:
            result = run_backtest_for_ticker(
                strategy_class=strategy_class,
                symbol=ticker,
                start_date=start_date,
                end_date=end_date
            )
            
            if result and result.get('status') == 'success':
                all_results.append(result)
                sharpe_str = f"{result['sharpe_ratio']:.2f}" if result['sharpe_ratio'] else "N/A"
                print(f"  {strategy_name}: {result['pnl_pct']:+.2f}% (夏普: {sharpe_str})")
            else:
                print(f"  {strategy_name}: 错误 - {result.get('error', 'Unknown') if result else 'No result'}")
    
    # 生成汇总报告
    report = {
        'timestamp': datetime.now().isoformat(),
        'backtest_period': {
            'start': start_date,
            'end': end_date,
            'days': 365
        },
        'alpha_candidates': alpha_candidates,
        'results': all_results,
        'summary': generate_summary(all_results)
    }
    
    # 保存报告
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = results_dir / f'scheduled_backtest_{timestamp}.json'
    
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n报告已保存: {report_file}")
    
    # 输出汇总
    print("\n" + "="*60)
    print("回测汇总")
    print("="*60)
    summary = report['summary']
    print(f"总回测次数: {summary['total_backtests']}")
    print(f"成功: {summary['successful']}")
    print(f"最佳收益: {summary['best_return']}")
    print(f"最差收益: {summary['worst_return']}")
    print(f"平均收益: {summary['avg_return']}")
    
    if summary['top_performers']:
        print("\n最佳表现:")
        for p in summary['top_performers'][:3]:
            print(f"  {p['symbol']} ({p['strategy']}): {p['pnl_pct']:+.2f}%")
    
    print("\n" + "="*60)
    print("定时回测完成 ✓")
    print("="*60)
    
    return report


def generate_summary(results):
    """生成汇总统计"""
    successful = [r for r in results if r.get('status') == 'success']
    
    if not successful:
        return {
            'total_backtests': len(results),
            'successful': 0,
            'best_return': 'N/A',
            'worst_return': 'N/A',
            'avg_return': 'N/A',
            'top_performers': []
        }
    
    returns = [r['pnl_pct'] for r in successful]
    
    # 排序获取最佳表现
    sorted_results = sorted(successful, key=lambda x: x['pnl_pct'], reverse=True)
    
    return {
        'total_backtests': len(results),
        'successful': len(successful),
        'best_return': f"{max(returns):+.2f}%",
        'worst_return': f"{min(returns):+.2f}%",
        'avg_return': f"{sum(returns)/len(returns):+.2f}%",
        'top_performers': [
            {
                'symbol': r['symbol'],
                'strategy': r['strategy'],
                'pnl_pct': r['pnl_pct'],
                'sharpe_ratio': r.get('sharpe_ratio')
            }
            for r in sorted_results[:5]
        ]
    }


def main():
    """主入口"""
    try:
        report = run_scheduled_backtest()
        return 0
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
