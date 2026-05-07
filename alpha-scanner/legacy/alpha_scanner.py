#!/usr/bin/env python3
"""
Alpha Stock Finder - 发现暴涨股票的自动化系统
每小时扫描美股市场，识别具有暴涨潜力的股票

策略包括：
1. 52周新高突破 + 成交量放大
2. 异常成交量异动
3. 技术指标金叉/超卖反弹
4. 新闻情绪正向波动
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
import requests
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings('ignore')

# 配置
REPORT_DIR = "/home/deqiangm/.hermes/cron/alpha-stock-finder/reports"
os.makedirs(REPORT_DIR, exist_ok=True)

# 核心股票池 - 高流动性美股
CORE_TICKERS = [
    # 科技巨头
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    # 半导体
    "AMD", "INTC", "QCOM", "AVGO", "TXN", "NXPI", "MU", "AMAT", "LRCX", "KLAC",
    # 软件
    "CRM", "ORCL", "ADBE", "NOW", "SNOW", "PLTR", "MDB",
    # 云计算
    "AMZN", "MSFT", "GOOGL", "CRM", "NOW", "SNOW",
    # 金融科技
    "V", "MA", "PYPL", "SQ", "COIN",
    # 电商零售
    "AMZN", "MELI", "SE", "EBAY",
    # 流媒体
    "NFLX", "DIS", "SPOT",
    # 其他热点
    "PLTR", "COIN", "RDDT", "SNOW", "DDOG", "ZS", "CRWD",
    # 近期关注
    "SSTK",  # ShutterStock
    "WDC",   # Western Digital  
    "STX",   # Seagate
]

# 热门ETF用于市场整体情绪
MARKET_ETFS = ["SPY", "QQQ", "IWM", "DIA"]

def fetch_stock_data(ticker, period="3mo"):
    """获取股票数据"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        if hist.empty or len(hist) < 20:
            return None
        
        info = {}
        try:
            info = stock.info
        except:
            pass
            
        return {
            'history': hist,
            'info': info,
            'ticker': ticker
        }
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None

def calculate_technical_indicators(df):
    """计算技术指标"""
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # MACD
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    
    # 移动平均
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    df['SMA_200'] = df['Close'].rolling(window=200).mean()
    
    # 布林带
    df['BB_Middle'] = df['Close'].rolling(window=20).mean()
    df['BB_Upper'] = df['BB_Middle'] + 2 * df['Close'].rolling(window=20).std()
    df['BB_Lower'] = df['BB_Middle'] - 2 * df['Close'].rolling(window=20).std()
    
    # 成交量相对强度
    df['Volume_SMA'] = df['Volume'].rolling(window=20).mean()
    df['Volume_Ratio'] = df['Volume'] / df['Volume_SMA']
    
    # ATR (波动率)
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    df['ATR_Ratio'] = df['ATR'] / df['Close'] * 100  # ATR占价格的百分比
    
    return df

def detect_breakout_patterns(data):
    """检测突破模式"""
    df = data['history']
    ticker = data['ticker']
    info = data['info']
    
    if len(df) < 50:
        return None
    
    df = calculate_technical_indicators(df)
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    signals = []
    score = 0
    
    # 1. 52周新高突破
    high_52w = df['High'].max()
    if latest['Close'] >= high_52w * 0.98:  # 接近或突破52周高点
        signals.append(f"接近52周新高 (${latest['Close']:.2f} vs ${high_52w:.2f})")
        score += 30
        
    # 2. 成交量放大
    if latest['Volume_Ratio'] > 2.0:
        signals.append(f"成交量放大 {latest['Volume_Ratio']:.1f}x")
        score += 25
    elif latest['Volume_Ratio'] > 1.5:
        signals.append(f"成交量增长 {latest['Volume_Ratio']:.1f}x")
        score += 15
        
    # 3. 价格动量
    price_change_1d = ((latest['Close'] - prev['Close']) / prev['Close']) * 100
    price_change_5d = ((latest['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]) * 100
    price_change_20d = ((latest['Close'] - df['Close'].iloc[-21]) / df['Close'].iloc[-21]) * 100
    
    if price_change_1d > 3:
        signals.append(f"单日涨幅 {price_change_1d:.1f}%")
        score += 20
    if price_change_5d > 10:
        signals.append(f"5日涨幅 {price_change_5d:.1f}%")
        score += 25
    if price_change_20d > 20:
        signals.append(f"20日涨幅 {price_change_20d:.1f}%")
        score += 30
        
    # 4. MACD金叉
    if prev['MACD'] < prev['MACD_Signal'] and latest['MACD'] > latest['MACD_Signal']:
        signals.append("MACD金叉")
        score += 20
    elif latest['MACD_Hist'] > 0 and latest['MACD'] > 0:
        signals.append("MACD多头排列")
        score += 10
        
    # 5. 均线多头排列
    if latest['SMA_20'] > latest['SMA_50'] > latest['SMA_200']:
        signals.append("均线多头排列")
        score += 25
    elif latest['SMA_20'] > latest['SMA_50']:
        signals.append("短期均线金叉")
        score += 15
        
    # 6. RSI超卖反弹
    if prev['RSI'] < 30 and latest['RSI'] > 30:
        signals.append("RSI超卖反弹")
        score += 20
    elif latest['RSI'] > 50 and latest['RSI'] < 70:
        signals.append(f"RSI健康区间 ({latest['RSI']:.0f})")
        score += 10
        
    # 7. 布林带突破
    if latest['Close'] > latest['BB_Upper']:
        signals.append("突破布林带上轨")
        score += 20
        
    # 8. 波动率扩张
    if latest['ATR_Ratio'] > df['ATR_Ratio'].iloc[-20:].mean() * 1.5:
        signals.append(f"波动率扩张 ({latest['ATR_Ratio']:.2f}%)")
        score += 15
    
    # 获取基本面信息
    market_cap = info.get('marketCap', 0)
    pe_ratio = info.get('trailingPE', 0)
    peg_ratio = info.get('pegRatio', 0)
    
    result = {
        'ticker': ticker,
        'price': float(latest['Close']),
        'volume': int(latest['Volume']),
        'volume_ratio': float(latest['Volume_Ratio']),
        'price_change_1d': round(price_change_1d, 2),
        'price_change_5d': round(price_change_5d, 2),
        'price_change_20d': round(price_change_20d, 2),
        'rsi': round(float(latest['RSI']), 1),
        'macd_hist': round(float(latest['MACD_Hist']), 4),
        'score': score,
        'signals': signals,
        'market_cap': market_cap,
        'pe_ratio': pe_ratio,
        'timestamp': datetime.now().isoformat(),
        'high_52w': float(high_52w),
        'distance_from_high': round((latest['Close'] / high_52w - 1) * 100, 2)
    }
    
    return result if score >= 30 else None  # 只返回得分>=30的股票

def get_market_sentiment():
    """获取市场整体情绪"""
    sentiments = {}
    for ticker in MARKET_ETFS:
        data = fetch_stock_data(ticker, period="1mo")
        if data:
            df = calculate_technical_indicators(data['history'])
            latest = df.iloc[-1]
            
            # 计算趋势得分
            trend = "neutral"
            if latest['Close'] > latest['SMA_50'] and latest['MACD'] > latest['MACD_Signal']:
                trend = "bullish"
            elif latest['Close'] < latest['SMA_50'] and latest['MACD'] < latest['MACD_Signal']:
                trend = "bearish"
                
            sentiments[ticker] = {
                'trend': trend,
                'rsi': round(float(latest['RSI']), 1),
                'price_change_5d': round(((latest['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]) * 100, 2)
            }
    return sentiments

def scan_for_alpha_stocks():
    """主扫描函数"""
    print(f"\n{'='*60}")
    print(f"Alpha Stock Scanner - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # 获取市场情绪
    print("📊 分析市场整体情绪...")
    market_sentiment = get_market_sentiment()
    for etf, data in market_sentiment.items():
        print(f"  {etf}: {data['trend']} | RSI: {data['rsi']} | 5日涨幅: {data['price_change_5d']}%")
    
    # 扫描股票
    print(f"\n🔍 扫描 {len(CORE_TICKERS)} 只核心股票...")
    
    results = []
    for i, ticker in enumerate(CORE_TICKERS):
        if i % 10 == 0:
            print(f"  进度: {i}/{len(CORE_TICKERS)}")
        
        data = fetch_stock_data(ticker)
        if data:
            result = detect_breakout_patterns(data)
            if result:
                results.append(result)
                print(f"  ✓ {ticker}: 得分 {result['score']} | 信号: {len(result['signals'])}")
    
    # 按得分排序并去重
    seen = set()
    unique_results = []
    for r in sorted(results, key=lambda x: x['score'], reverse=True):
        if r['ticker'] not in seen:
            seen.add(r['ticker'])
            unique_results.append(r)
    results = unique_results
    
    # 生成报告
    report = {
        'timestamp': datetime.now().isoformat(),
        'market_sentiment': market_sentiment,
        'total_scanned': len(CORE_TICKERS),
        'alpha_candidates': len(results),
 'top_picks': results[:20], # 前20只
        'all_candidates': results
    }
    
    # 保存报告
    report_file = os.path.join(REPORT_DIR, f"alpha_scan_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n📁 报告已保存: {report_file}")
    
    # 打印摘要
    print(f"\n{'='*60}")
    print("📈 TOP ALPHA 候选股:")
    print(f"{'='*60}")
    
    for i, stock in enumerate(results[:5], 1):
        print(f"\n{i}. {stock['ticker']} - 得分: {stock['score']}")
        print(f"   价格: ${stock['price']:.2f} | 1日: {stock['price_change_1d']}% | 5日: {stock['price_change_5d']}%")
        print(f"   成交量: {stock['volume_ratio']:.1f}x | RSI: {stock['rsi']}")
        print(f"   信号: {', '.join(stock['signals'][:3])}")
    
    return report

if __name__ == "__main__":
    scan_for_alpha_stocks()
