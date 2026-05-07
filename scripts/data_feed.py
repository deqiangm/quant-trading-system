#!/usr/bin/env python3
"""
数据源配置与测试脚本
测试yfinance数据获取功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

def fetch_stock_data(symbol, start_date, end_date):
    """
    从Yahoo Finance获取股票数据
    
    Args:
        symbol: 股票代码 (如 'AAPL')
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
    
    Returns:
        DataFrame with OHLCV data
    """
    print(f"正在获取 {symbol} 数据 ({start_date} 至 {end_date})...")
    
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start_date, end=end_date)
    
    if df.empty:
        print(f"错误: 未能获取 {symbol} 数据")
        return None
    
    # 标准化列名
    df.columns = [c.lower().replace(' ', '_') for c in df.columns]
    
    print(f"成功获取 {len(df)} 条记录")
    print(f"日期范围: {df.index[0].strftime('%Y-%m-%d')} 至 {df.index[-1].strftime('%Y-%m-%d')}")
    
    return df

def validate_data(df):
    """验证数据质量"""
    print("\n=== 数据验证 ===")
    
    # 检查缺失值
    missing = df.isnull().sum()
    if missing.any():
        print("警告: 发现缺失值:")
        print(missing[missing > 0])
    else:
        print("✓ 无缺失值")
    
    # 检查价格合理性
    if (df['close'] <= 0).any():
        print("警告: 存在非正价格")
    else:
        print("✓ 价格数据正常")
    
    # 检查成交量
    if (df['volume'] < 0).any():
        print("警告: 存在负成交量")
    else:
        print("✓ 成交量数据正常")
    
    # 数据统计
    print(f"\n数据统计:")
    print(f"  收盘价范围: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
    print(f"  平均成交量: {df['volume'].mean():,.0f}")
    
    return True

def main():
    """主测试函数"""
    print("=" * 50)
    print("数据源配置测试")
    print("=" * 50)
    
    # 测试数据获取
    symbol = "AAPL"
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    
    df = fetch_stock_data(symbol, start_date, end_date)
    
    if df is not None:
        validate_data(df)
        
        # 保存样本数据
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        os.makedirs(data_dir, exist_ok=True)
        sample_path = os.path.join(data_dir, f'{symbol}_sample.csv')
        df.to_csv(sample_path)
        print(f"\n样本数据已保存至: {sample_path}")
        
        # 显示数据预览
        print("\n数据预览 (前5行):")
        print(df.head())
        
        print("\n" + "=" * 50)
        print("数据源配置测试完成 ✓")
        print("=" * 50)
        return 0
    
    return 1

if __name__ == "__main__":
    sys.exit(main())
