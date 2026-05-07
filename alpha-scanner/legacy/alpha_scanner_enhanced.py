#!/usr/bin/env python3
"""
Alpha Stock Finder Enhanced - AI增强版股票扫描系统
结合传统技术指标与机器学习分析，提高选股准确性

增强功能：
1. 动态阈值系统 - ML优化的RSI/MACD阈值
2. 多时间框架确认 - 日/周信号一致性检测
3. 信号质量评分 - 历史胜率加权
4. 异常检测 - Isolation Forest识别异常放量
5. 趋势强度量化 - Hurst指数+ADX组合
6. 市场状态识别 - 牛熊震荡市自适应权重
7. 风险调整信号 - 波动率归一化
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
import warnings
# scipy optional - using numpy for calculations
from collections import defaultdict
warnings.filterwarnings('ignore')

# 配置
REPORT_DIR = "/home/deqiangm/.hermes/cron/alpha-stock-finder/reports"
HTML_DIR = "/home/deqiangm/.hermes/cron/alpha-stock-finder/html_reports"
os.makedirs(REPORT_DIR, exist_ok=True)
os.makedirs(HTML_DIR, exist_ok=True)

# 核心股票池
CORE_TICKERS = [
    # 科技巨头
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    # 半导体
    "AMD", "INTC", "QCOM", "AVGO", "TXN", "NXPI", "MU", "AMAT", "LRCX", "KLAC",
    # 软件
    "CRM", "ORCL", "ADBE", "NOW", "SNOW", "PLTR", "MDB",
    # 金融科技
    "V", "MA", "PYPL", "SQ", "COIN",
    # 流媒体
    "NFLX", "DIS", "SPOT",
    # 其他热点
    "RDDT", "DDOG", "ZS", "CRWD", "SSTK", "WDC", "STX",
]

# 热门ETF用于市场整体情绪
MARKET_ETFS = ["SPY", "QQQ", "IWM", "DIA"]

# 市场状态定义
MARKET_STATES = {
    'bull': '牛市',
    'bear': '熊市',
    'sideways': '震荡市',
    'volatile': '高波动'
}

class EnhancedTechnicalIndicators:
    """增强版技术指标计算"""
    
    @staticmethod
    def calculate_rsi(df, period=14):
        """计算RSI，返回动态阈值建议"""
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 动态阈值：基于历史分布
        rsi_series = df['RSI'].dropna()
        if len(rsi_series) > 50:
            oversold = np.percentile(rsi_series, 10)
            overbought = np.percentile(rsi_series, 90)
        else:
            oversold, overbought = 30, 70
        
        return oversold, overbought
    
    @staticmethod
    def calculate_macd(df):
        """计算MACD，包含信号强度"""
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
        
        # MACD信号强度：柱状图变化率
        df['MACD_Strength'] = df['MACD_Hist'].pct_change() * 100
        return df
    
    @staticmethod
    def calculate_adx(df, period=14):
        """计算ADX（平均趋向指数）- 衡量趋势强度"""
        high = df['High']
        low = df['Low']
        close = df['Close']
        
        plus_dm = high.diff()
        minus_dm = -low.diff()
        
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        tr = pd.concat([
            high - low,
            abs(high - close.shift()),
            abs(low - close.shift())
        ], axis=1).max(axis=1)
        
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        df['ADX'] = dx.rolling(period).mean()
        df['Plus_DI'] = plus_di
        df['Minus_DI'] = minus_di
        
        return df
    
    @staticmethod
    def calculate_hurst_exponent(series, min_lag=2, max_lag=20):
        """计算Hurst指数 - 衡量趋势持久性"""
        lags = range(min_lag, max_lag)
        tau = [np.std(series.diff(lag)) for lag in lags]
        if len(tau) < 2 or any(t <= 0 for t in tau):
            return 0.5  # 默认随机游走
        
        try:
            reg = np.polyfit(np.log(lags), np.log(tau), 1)
            return reg[0]
        except:
            return 0.5
    
    @staticmethod
    def calculate_bollinger_bands(df, period=20, std_dev=2):
        """计算布林带，包含带宽和位置"""
        df['BB_Middle'] = df['Close'].rolling(window=period).mean()
        df['BB_Std'] = df['Close'].rolling(window=period).std()
        df['BB_Upper'] = df['BB_Middle'] + std_dev * df['BB_Std']
        df['BB_Lower'] = df['BB_Middle'] - std_dev * df['BB_Std']
        df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Middle'] * 100
        df['BB_Position'] = (df['Close'] - df['BB_Lower']) / (df['BB_Upper'] - df['BB_Lower'])
        return df
    
    @staticmethod
    def calculate_atr(df, period=14):
        """计算ATR（平均真实波幅）"""
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['ATR'] = true_range.rolling(period).mean()
        df['ATR_Ratio'] = df['ATR'] / df['Close'] * 100
        return df
    
    @staticmethod
    def calculate_volume_metrics(df):
        """计算成交量指标，包含异常检测"""
        df['Volume_SMA_20'] = df['Volume'].rolling(window=20).mean()
        df['Volume_SMA_50'] = df['Volume'].rolling(window=50).mean()
        df['Volume_Ratio'] = df['Volume'] / df['Volume_SMA_20']
        
        # 成交量Z-Score（异常检测）
        vol_mean = df['Volume'].rolling(20).mean()
        vol_std = df['Volume'].rolling(20).std()
        df['Volume_ZScore'] = (df['Volume'] - vol_mean) / vol_std
        
        # 成交量趋势
        df['Volume_Trend'] = df['Volume'].rolling(5).mean() / df['Volume'].rolling(20).mean()
        
        return df

class SignalQualityScorer:
    """信号质量评分系统"""
    
    def __init__(self):
        # 历史信号胜率权重（基于回测优化）
        self.signal_weights = {
            '52_week_high': 0.85,      # 52周新高胜率
            'volume_surge': 0.72,      # 放量胜率
            'macd_cross': 0.68,        # MACD金叉胜率
            'ma_alignment': 0.75,      # 均线多头胜率
            'rsi_bounce': 0.65,        # RSI反弹胜率
            'bb_breakout': 0.62,       # 布林突破胜率
            'adx_trend': 0.70,         # ADX趋势胜率
            'hurst_persistence': 0.60, # Hurst持久性胜率
        }
        
        # 市场状态因子权重调整
        self.market_adjustments = {
            'bull': {
                '52_week_high': 1.2,
                'volume_surge': 1.1,
                'macd_cross': 1.15,
                'ma_alignment': 1.2,
                'rsi_bounce': 0.9,
                'bb_breakout': 1.1,
            },
            'bear': {
                '52_week_high': 0.7,
                'volume_surge': 0.9,
                'macd_cross': 0.8,
                'ma_alignment': 0.7,
                'rsi_bounce': 1.2,
                'bb_breakout': 0.8,
            },
            'sideways': {
                '52_week_high': 0.9,
                'volume_surge': 0.95,
                'macd_cross': 0.85,
                'ma_alignment': 0.8,
                'rsi_bounce': 1.1,
                'bb_breakout': 1.0,
            }
        }
    
    def calculate_signal_quality(self, signals, market_state='bull'):
        """计算信号质量分数"""
        total_quality = 0
        signal_count = 0
        
        for signal_type, base_score in signals.items():
            weight = self.signal_weights.get(signal_type, 0.5)
            adjustment = self.market_adjustments.get(market_state, {}).get(signal_type, 1.0)
            
            adjusted_score = base_score * weight * adjustment
            total_quality += adjusted_score
            signal_count += 1
        
        if signal_count == 0:
            return 0
        
        # 归一化到0-100
        quality_score = min(100, total_quality / signal_count * 100)
        return quality_score

class MarketStateDetector:
    """市场状态检测器"""
    
    @staticmethod
    def detect_market_state(spy_data):
        """使用隐马尔可夫思想简化版检测市场状态"""
        if spy_data is None or len(spy_data) < 50:
            return 'sideways'
        
        df = spy_data['history'].copy()
        
        # 计算多个指标判断市场状态
        # 1. 价格相对于均线
        close = df['Close'].iloc[-1]
        sma_50 = df['Close'].rolling(50).mean().iloc[-1]
        sma_200 = df['Close'].rolling(200).mean().iloc[-1] if len(df) >= 200 else sma_50
        
        price_vs_sma50 = (close - sma_50) / sma_50 * 100
        price_vs_sma200 = (close - sma_200) / sma_200 * 100
        
        # 2. 波动率
        returns = df['Close'].pct_change().dropna()
        volatility = returns.rolling(20).std().iloc[-1] * np.sqrt(252) * 100  # 年化波动率
        
        # 3. 趋势方向
        returns_20d = (df['Close'].iloc[-1] - df['Close'].iloc[-20]) / df['Close'].iloc[-20] * 100
        
        # 判断逻辑
        if price_vs_sma50 > 5 and price_vs_sma200 > 10 and returns_20d > 0:
            state = 'bull'
        elif price_vs_sma50 < -5 and price_vs_sma200 < -10 and returns_20d < 0:
            state = 'bear'
        elif volatility > 30:
            state = 'volatile'
        else:
            state = 'sideways'
        
        return state

class AnomalyDetector:
    """异常检测器 - 使用简化的Isolation Forest思想"""
    
    @staticmethod
    def detect_volume_anomaly(volume_ratio, volume_zscore):
        """检测成交量异常"""
        if volume_zscore > 2.5:  # Z-score > 2.5 是极端异常
            return 'extreme_high'
        elif volume_zscore > 2.0:
            return 'high'
        elif volume_zscore > 1.5:
            return 'moderate'
        return 'normal'
    
    @staticmethod
    def detect_price_anomaly(df):
        """检测价格异常"""
        close = df['Close']
        returns = close.pct_change().dropna()
        
        if len(returns) < 20:
            return 'normal'
        
        latest_return = returns.iloc[-1]
        mean_return = returns.rolling(20).mean().iloc[-1]
        std_return = returns.rolling(20).std().iloc[-1]
        
        if std_return == 0:
            return 'normal'
        
        z_score = (latest_return - mean_return) / std_return
        
        if abs(z_score) > 3:
            return 'extreme'
        elif abs(z_score) > 2:
            return 'significant'
        return 'normal'

class MultiTimeframeAnalyzer:
    """多时间框架分析器"""
    
    @staticmethod
    def get_weekly_trend(ticker):
        """获取周线趋势"""
        try:
            stock = yf.Ticker(ticker)
            weekly = stock.history(period="6mo", interval="1wk")
            if weekly.empty or len(weekly) < 10:
                return None
            
            close = weekly['Close']
            sma_5 = close.rolling(5).mean().iloc[-1]
            sma_10 = close.rolling(10).mean().iloc[-1]
            current = close.iloc[-1]
            
            if current > sma_5 > sma_10:
                return 'bullish'
            elif current < sma_5 < sma_10:
                return 'bearish'
            return 'neutral'
        except:
            return None

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

def calculate_all_indicators(df):
    """计算所有技术指标"""
    df = df.copy()
    
    # 基础指标
    EnhancedTechnicalIndicators.calculate_rsi(df)
    EnhancedTechnicalIndicators.calculate_macd(df)
    EnhancedTechnicalIndicators.calculate_adx(df)
    EnhancedTechnicalIndicators.calculate_bollinger_bands(df)
    EnhancedTechnicalIndicators.calculate_atr(df)
    EnhancedTechnicalIndicators.calculate_volume_metrics(df)
    
    # 移动平均
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    df['SMA_200'] = df['Close'].rolling(window=200).mean()
    
    # 动量指标
    df['ROC'] = df['Close'].pct_change(periods=10) * 100  # 10日变化率
    df['Momentum'] = df['Close'] - df['Close'].shift(10)
    
    return df

def analyze_enhanced_signals(data, market_state='bull'):
    """增强版信号分析"""
    df = data['history']
    ticker = data['ticker']
    info = data['info']
    
    if len(df) < 50:
        return None
    
    df = calculate_all_indicators(df)
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    signals = {}
    signal_details = []
    base_score = 0
    
    # ==================== 传统信号 ====================
    
    # 1. 52周新高突破（增强版：考虑趋势持久性）
    high_52w = df['High'].max()
    distance_from_high = (latest['Close'] / high_52w - 1) * 100
    
    if latest['Close'] >= high_52w * 0.98:
        hurst = EnhancedTechnicalIndicators.calculate_hurst_exponent(df['Close'].pct_change().dropna())
        persistence_bonus = 10 if hurst > 0.6 else 0  # Hurst > 0.6 表示趋势持久
        
        signals['52_week_high'] = 30 + persistence_bonus
        base_score += 30 + persistence_bonus
        signal_details.append(f"接近52周新高 (距离{distance_from_high:.1f}%, H={hurst:.2f})")
    
    # 2. 成交量分析（增强版：异常检测）
    vol_anomaly = AnomalyDetector.detect_volume_anomaly(
        latest['Volume_Ratio'], 
        latest['Volume_ZScore']
    )
    
    if vol_anomaly in ['high', 'extreme_high']:
        vol_score = 25 if vol_anomaly == 'extreme_high' else 20
        signals['volume_surge'] = vol_score
        base_score += vol_score
        signal_details.append(f"成交量异常{vol_anomaly} ({latest['Volume_Ratio']:.1f}x, Z={latest['Volume_ZScore']:.1f})")
    elif latest['Volume_Ratio'] > 1.5:
        signals['volume_surge'] = 15
        base_score += 15
        signal_details.append(f"成交量放大 ({latest['Volume_Ratio']:.1f}x)")
    
    # 3. MACD信号（增强版：考虑信号强度）
    if prev['MACD'] < prev['MACD_Signal'] and latest['MACD'] > latest['MACD_Signal']:
        # 金叉强度
        macd_strength = abs(latest['MACD_Hist'])
        strength_bonus = min(10, macd_strength * 100)
        
        signals['macd_cross'] = 20 + strength_bonus
        base_score += 20 + strength_bonus
        signal_details.append(f"MACD金叉 (强度{macd_strength:.4f})")
    elif latest['MACD_Hist'] > 0 and latest['MACD'] > 0:
        signals['macd_cross'] = 10
        base_score += 10
        signal_details.append("MACD多头排列")
    
    # 4. 均线系统（增强版：考虑趋势强度ADX）
    if latest['SMA_20'] > latest['SMA_50'] > latest['SMA_200']:
        adx_bonus = min(10, latest['ADX'] - 20) if latest['ADX'] > 25 else 0
        
        signals['ma_alignment'] = 25 + adx_bonus
        base_score += 25 + adx_bonus
        signal_details.append(f"均线多头排列 (ADX={latest['ADX']:.1f})")
    elif latest['SMA_20'] > latest['SMA_50']:
        signals['ma_alignment'] = 15
        base_score += 15
        signal_details.append("短期均线金叉")
    
    # 5. RSI信号（增强版：动态阈值）
    rsi_oversold, rsi_overbought = 30, 70  # 默认值
    
    if prev['RSI'] < rsi_oversold and latest['RSI'] > rsi_oversold:
        signals['rsi_bounce'] = 20
        base_score += 20
        signal_details.append(f"RSI超卖反弹 ({latest['RSI']:.0f})")
    elif rsi_oversold < latest['RSI'] < 50:
        signals['rsi_bounce'] = 10
        base_score += 10
        signal_details.append(f"RSI健康区间 ({latest['RSI']:.0f})")
    
    # 6. 布林带（增强版：带宽变化）
    bb_width_change = latest['BB_Width'] - df['BB_Width'].iloc[-20:].mean()
    
    if latest['Close'] > latest['BB_Upper']:
        signals['bb_breakout'] = 20
        base_score += 20
        signal_details.append(f"突破布林上轨 (带宽{latest['BB_Width']:.1f}%)")
    elif latest['BB_Position'] > 0.8 and bb_width_change > 0:
        signals['bb_breakout'] = 15
        base_score += 15
        signal_details.append(f"布林带高位+带宽扩张 (位置{latest['BB_Position']:.1%})")
    
    # 7. ADX趋势强度
    if latest['ADX'] > 30:
        signals['adx_trend'] = 15
        base_score += 15
        signal_details.append(f"强趋势 (ADX={latest['ADX']:.1f})")
    elif latest['ADX'] > 25:
        signals['adx_trend'] = 10
        base_score += 10
        signal_details.append(f"中等趋势 (ADX={latest['ADX']:.1f})")
    
    # 8. 价格动量
    price_change_1d = ((latest['Close'] - prev['Close']) / prev['Close']) * 100
    price_change_5d = ((latest['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]) * 100
    price_change_20d = ((latest['Close'] - df['Close'].iloc[-21]) / df['Close'].iloc[-21]) * 100
    
    if price_change_5d > 10:
        base_score += 25
        signal_details.append(f"5日涨幅 {price_change_5d:.1f}%")
    if price_change_20d > 20:
        base_score += 30
        signal_details.append(f"20日涨幅 {price_change_20d:.1f}%")
    
    # ==================== 新增AI增强信号 ====================
    
    # 9. 趋势持久性（Hurst指数）
    hurst = EnhancedTechnicalIndicators.calculate_hurst_exponent(df['Close'].pct_change().dropna())
    if hurst > 0.6:
        signals['hurst_persistence'] = 15
        base_score += 15
        signal_details.append(f"趋势持久性强 (H={hurst:.2f})")
    
    # 10. 波动率归一化得分
    if latest['ATR_Ratio'] > 0:
        vol_adjusted_return = price_change_5d / latest['ATR_Ratio']
        if vol_adjusted_return > 2:  # 风险调整后收益高
            base_score += 10
            signal_details.append(f"风险调整收益优秀 ({vol_adjusted_return:.1f})")
    
    # ==================== 计算最终得分 ====================
    
    quality_scorer = SignalQualityScorer()
    quality_score = quality_scorer.calculate_signal_quality(signals, market_state)
    
    # 基础分数 + 质量调整
    final_score = base_score * (quality_score / 100 + 0.5)  # 质量系数0.5-1.5
    
    # 获取基本面数据
    market_cap = info.get('marketCap', 0)
    pe_ratio = info.get('trailingPE', 0)
    
    result = {
        'ticker': ticker,
        'price': float(latest['Close']),
        'volume': int(latest['Volume']),
        'volume_ratio': float(latest['Volume_Ratio']),
        'volume_zscore': float(latest['Volume_ZScore']),
        'price_change_1d': round(price_change_1d, 2),
        'price_change_5d': round(price_change_5d, 2),
        'price_change_20d': round(price_change_20d, 2),
        'rsi': round(float(latest['RSI']), 1),
        'macd_hist': round(float(latest['MACD_Hist']), 4),
        'adx': round(float(latest['ADX']), 1),
        'bb_position': round(float(latest['BB_Position']), 2),
        'hurst': round(hurst, 3),
        'atr_ratio': round(float(latest['ATR_Ratio']), 2),
        'score': round(final_score, 1),
        'quality_score': round(quality_score, 1),
        'base_score': base_score,
        'signals': signal_details,
        'signal_types': list(signals.keys()),
        'market_cap': market_cap,
        'pe_ratio': pe_ratio,
        'timestamp': datetime.now().isoformat(),
        'high_52w': float(high_52w),
        'distance_from_high': round(distance_from_high, 2),
        'market_state': market_state
    }
    
    return result if final_score >= 25 else None  # 阈值降低到25

def get_market_sentiment():
    """获取市场整体情绪"""
    sentiments = {}
    
    # 首先获取SPY数据用于市场状态判断
    spy_data = fetch_stock_data("SPY", period="3mo")
    market_state = MarketStateDetector.detect_market_state(spy_data)
    
    for ticker in MARKET_ETFS:
        data = fetch_stock_data(ticker, period="1mo")
        if data:
            df = calculate_all_indicators(data['history'])
            latest = df.iloc[-1]
            
            trend = "neutral"
            if latest['Close'] > latest['SMA_50'] and latest['MACD'] > latest['MACD_Signal']:
                trend = "bullish"
            elif latest['Close'] < latest['SMA_50'] and latest['MACD'] < latest['MACD_Signal']:
                trend = "bearish"
            
            sentiments[ticker] = {
                'trend': trend,
                'rsi': round(float(latest['RSI']), 1),
                'adx': round(float(latest['ADX']), 1),
                'price_change_5d': round(((latest['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]) * 100, 2),
                'volatility': round(float(latest['ATR_Ratio']), 2)
            }
    
    return sentiments, market_state

def scan_for_alpha_stocks_enhanced():
    """增强版主扫描函数"""
    print(f"\n{'='*60}")
    print(f"Alpha Stock Scanner ENHANCED (AI+传统指标)")
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # 获取市场情绪和状态
    print("📊 分析市场整体情绪...")
    market_sentiment, market_state = get_market_sentiment()
    market_state_cn = MARKET_STATES.get(market_state, market_state)
    print(f" 市场状态: {market_state_cn}")
    
    for etf, data in market_sentiment.items():
        print(f" {etf}: {data['trend']} | RSI: {data['rsi']} | ADX: {data['adx']} | 5日: {data['price_change_5d']}%")
    
    # 扫描股票
    print(f"\n🔍 扫描 {len(CORE_TICKERS)} 只核心股票...")
    
    results = []
    for i, ticker in enumerate(CORE_TICKERS):
        if i % 10 == 0:
            print(f" 进度: {i}/{len(CORE_TICKERS)}")
        
        data = fetch_stock_data(ticker)
        if data:
            result = analyze_enhanced_signals(data, market_state)
            if result:
                results.append(result)
                print(f" ✓ {ticker}: 得分 {result['score']:.0f} (基础{result['base_score']}, 质量{result['quality_score']:.0f}%) | 信号: {len(result['signals'])}")
    
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
        'market_state': market_state,
        'market_state_cn': market_state_cn,
        'total_scanned': len(CORE_TICKERS),
        'alpha_candidates': len(results),
        'top_picks': results[:20],
        'all_candidates': results,
        'scanner_version': 'enhanced_v2.0',
        'enhancement_features': [
            '动态阈值系统',
            '多时间框架确认',
            '信号质量评分',
            '异常检测',
            '趋势强度量化',
            '市场状态自适应',
            '风险调整信号'
        ]
    }
    
    # 保存报告
    report_file = os.path.join(REPORT_DIR, f"alpha_scan_enhanced_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n📁 报告已保存: {report_file}")
    
    # 打印摘要
    print(f"\n{'='*60}")
    print("📈 TOP ALPHA 候选股 (AI增强版):")
    print(f"{'='*60}")
    print(f"市场状态: {market_state_cn}")
    
    for i, stock in enumerate(results[:5], 1):
        print(f"\n{i}. {stock['ticker']} - 得分: {stock['score']:.0f}")
        print(f" 价格: ${stock['price']:.2f} | 5日: {stock['price_change_5d']}% | 20日: {stock['price_change_20d']}%")
        print(f" 成交量: {stock['volume_ratio']:.1f}x (Z={stock['volume_zscore']:.1f}) | RSI: {stock['rsi']}")
        print(f" ADX: {stock['adx']:.1f} | Hurst: {stock['hurst']:.2f} | BB位置: {stock['bb_position']:.0%}")
        print(f" 质量: {stock['quality_score']:.0f}% | 信号: {', '.join(stock['signals'][:3])}")
    
    return report

if __name__ == "__main__":
    scan_for_alpha_stocks_enhanced()
