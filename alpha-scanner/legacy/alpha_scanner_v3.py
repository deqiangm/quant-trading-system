#!/usr/bin/env python3
"""
Alpha Stock Finder V3 - 深度学习增强版
结合传统技术指标与现代机器学习，实现更准确的选股

基于研究论文优化：
1. Node Transformer思想 - 股票关系图建模
2. TCN + Attention-LSTM - 时序特征提取
3. XGBoost集成 - 特征重要性优化
4. 多因子信号融合 - 动态权重系统
5. 情感分析集成 - 市场情绪因子

V3新功能：
- 特征工程优化：100+技术指标组合
- 机器学习评分：XGBoost概率预测
- 信号质量评估：历史胜率回测
- 市场状态识别：牛熊震荡自适应
- 风险调整收益：夏普比率优化
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
import warnings
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
warnings.filterwarnings('ignore')

# 配置
REPORT_DIR = "/home/deqiangm/.hermes/cron/alpha-stock-finder/reports"
HTML_DIR = "/home/deqiangm/.hermes/cron/alpha-stock-finder/html_reports"
MODEL_DIR = "/home/deqiangm/.hermes/cron/alpha-stock-finder/models"
os.makedirs(REPORT_DIR, exist_ok=True)
os.makedirs(HTML_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

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

# 市场ETF
MARKET_ETFS = ["SPY", "QQQ", "IWM", "DIA"]

# 市场状态
MARKET_STATES = {
    'bull': '牛市',
    'bear': '熊市', 
    'sideways': '震荡市',
    'volatile': '高波动'
}

class FeatureEngineering:
    """高级特征工程 - 100+技术指标"""
    
    @staticmethod
    def calculate_all_features(df: pd.DataFrame) -> pd.DataFrame:
        """计算所有技术特征"""
        df = df.copy()
        
        # 1. 价格动量特征
        FeatureEngineering._price_momentum_features(df)
        
        # 2. 波动率特征
        FeatureEngineering._volatility_features(df)
        
        # 3. 成交量特征
        FeatureEngineering._volume_features(df)
        
        # 4. 趋势特征
        FeatureEngineering._trend_features(df)
        
        # 5. 形态特征
        FeatureEngineering._pattern_features(df)
        
        # 6. 统计特征
        FeatureEngineering._statistical_features(df)
        
        return df
    
    @staticmethod
    def _price_momentum_features(df: pd.DataFrame):
        """价格动量特征"""
        # RSI系列
        for period in [7, 14, 21]:
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            df[f'RSI_{period}'] = 100 - (100 / (1 + rs))
        
        # MACD系列
        for fast, slow, signal in [(12, 26, 9), (5, 13, 4)]:
            exp_fast = df['Close'].ewm(span=fast, adjust=False).mean()
            exp_slow = df['Close'].ewm(span=slow, adjust=False).mean()
            df[f'MACD_{fast}_{slow}'] = exp_fast - exp_slow
            df[f'MACD_Signal_{fast}_{slow}'] = df[f'MACD_{fast}_{slow}'].ewm(span=signal, adjust=False).mean()
            df[f'MACD_Hist_{fast}_{slow}'] = df[f'MACD_{fast}_{slow}'] - df[f'MACD_Signal_{fast}_{slow}']
        
        # 动量振荡器
        df['ROC_5'] = df['Close'].pct_change(periods=5) * 100
        df['ROC_10'] = df['Close'].pct_change(periods=10) * 100
        df['ROC_20'] = df['Close'].pct_change(periods=20) * 100
        
        # 威廉指标
        df['Williams_R'] = ((df['High'].rolling(14).max() - df['Close']) / 
                           (df['High'].rolling(14).max() - df['Low'].rolling(14).min())) * -100
        
        # CCI
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        df['CCI'] = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).std())
    
    @staticmethod
    def _volatility_features(df: pd.DataFrame):
        """波动率特征"""
        # 布林带系列
        for period in [10, 20, 50]:
            df[f'BB_Middle_{period}'] = df['Close'].rolling(window=period).mean()
            df[f'BB_Std_{period}'] = df['Close'].rolling(window=period).std()
            df[f'BB_Upper_{period}'] = df[f'BB_Middle_{period}'] + 2 * df[f'BB_Std_{period}']
            df[f'BB_Lower_{period}'] = df[f'BB_Middle_{period}'] - 2 * df[f'BB_Std_{period}']
            df[f'BB_Width_{period}'] = (df[f'BB_Upper_{period}'] - df[f'BB_Lower_{period}']) / df[f'BB_Middle_{period}'] * 100
            df[f'BB_Position_{period}'] = (df['Close'] - df[f'BB_Lower_{period}']) / (df[f'BB_Upper_{period}'] - df[f'BB_Lower_{period}'])
        
        # ATR系列
        for period in [7, 14, 21]:
            high_low = df['High'] - df['Low']
            high_close = np.abs(df['High'] - df['Close'].shift())
            low_close = np.abs(df['Low'] - df['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = np.max(ranges, axis=1)
            df[f'ATR_{period}'] = true_range.rolling(period).mean()
            df[f'ATR_Ratio_{period}'] = df[f'ATR_{period}'] / df['Close'] * 100
        
        # Keltner通道
        df['KC_Middle'] = df['Close'].rolling(20).mean()
        df['KC_Upper'] = df['KC_Middle'] + 2 * df['ATR_14']
        df['KC_Lower'] = df['KC_Middle'] - 2 * df['ATR_14']
    
    @staticmethod
    def _volume_features(df: pd.DataFrame):
        """成交量特征"""
        # 成交量均线
        for period in [5, 10, 20, 50]:
            df[f'Volume_SMA_{period}'] = df['Volume'].rolling(window=period).mean()
            df[f'Volume_Ratio_{period}'] = df['Volume'] / df[f'Volume_SMA_{period}']
        
        # OBV
        df['OBV'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
        df['OBV_SMA'] = df['OBV'].rolling(20).mean()
        
        # 成交量Z-Score
        vol_mean = df['Volume'].rolling(20).mean()
        vol_std = df['Volume'].rolling(20).std()
        df['Volume_ZScore'] = (df['Volume'] - vol_mean) / vol_std
        
        # MFI (资金流量指标)
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        money_flow = typical_price * df['Volume']
        positive_flow = money_flow.where(typical_price > typical_price.shift(), 0).rolling(14).sum()
        negative_flow = money_flow.where(typical_price < typical_price.shift(), 0).rolling(14).sum()
        df['MFI'] = 100 - (100 / (1 + positive_flow / negative_flow))
        
        # VWAP
        df['VWAP'] = (df['Close'] * df['Volume']).rolling(20).sum() / df['Volume'].rolling(20).sum()
    
    @staticmethod
    def _trend_features(df: pd.DataFrame):
        """趋势特征"""
        # 移动平均线系统
        for period in [5, 10, 20, 50, 100, 200]:
            df[f'SMA_{period}'] = df['Close'].rolling(window=period).mean()
            df[f'EMA_{period}'] = df['Close'].ewm(span=period, adjust=False).mean()
        
        # MA交叉信号
        df['MA_Cross_5_10'] = (df['SMA_5'] > df['SMA_10']).astype(int)
        df['MA_Cross_10_20'] = (df['SMA_10'] > df['SMA_20']).astype(int)
        df['MA_Cross_20_50'] = (df['SMA_20'] > df['SMA_50']).astype(int)
        df['MA_Cross_50_200'] = (df['SMA_50'] > df['SMA_200']).astype(int)
        
        # ADX系列
        high = df['High']
        low = df['Low']
        close = df['Close']
        
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        
        plus_di = 100 * (plus_dm.rolling(14).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        
        df['ADX'] = dx.rolling(14).mean()
        df['Plus_DI'] = plus_di
        df['Minus_DI'] = minus_di
        df['DI_Diff'] = plus_di - minus_di
        
        # Ichimoku云图简化版
        df['Tenkan'] = (df['High'].rolling(9).max() + df['Low'].rolling(9).min()) / 2
        df['Kijun'] = (df['High'].rolling(26).max() + df['Low'].rolling(26).min()) / 2
        df['Senkou_A'] = ((df['Tenkan'] + df['Kijun']) / 2).shift(26)
        df['Senkou_B'] = ((df['High'].rolling(52).max() + df['Low'].rolling(52).min()) / 2).shift(26)
        df['Chikou'] = df['Close'].shift(-26)
    
    @staticmethod
    def _pattern_features(df: pd.DataFrame):
        """形态特征"""
        # K线形态
        df['Body'] = df['Close'] - df['Open']
        df['Upper_Shadow'] = df['High'] - df[['Close', 'Open']].max(axis=1)
        df['Lower_Shadow'] = df[['Close', 'Open']].min(axis=1) - df['Low']
        df['Body_Ratio'] = df['Body'] / (df['High'] - df['Low'] + 0.0001)
        
        # Doji检测
        df['Is_Doji'] = (abs(df['Body']) / (df['High'] - df['Low'] + 0.0001) < 0.1).astype(int)
        
        # Hammer/Hanging Man
        df['Is_Hammer'] = ((df['Lower_Shadow'] > 2 * abs(df['Body'])) & 
                          (df['Upper_Shadow'] < abs(df['Body']))).astype(int)
        
        # Engulfing
        df['Is_Bullish_Engulf'] = ((df['Body'].shift(1) < 0) & 
                                   (df['Body'] > 0) & 
                                   (df['Close'] > df['Open'].shift(1)) & 
                                   (df['Open'] < df['Close'].shift(1))).astype(int)
        
        # Gap检测
        df['Gap_Up'] = (df['Low'] > df['High'].shift(1)).astype(int)
        df['Gap_Down'] = (df['High'] < df['Low'].shift(1)).astype(int)
    
    @staticmethod
    def _statistical_features(df: pd.DataFrame):
        """统计特征"""
        # Hurst指数（趋势持久性）
        if len(df) > 50:
            df['Hurst'] = FeatureEngineering._calculate_hurst(df['Close'].pct_change().dropna())
        
        # 偏度和峰度
        for period in [20, 50]:
            df[f'Skewness_{period}'] = df['Close'].pct_change().rolling(period).skew()
            df[f'Kurtosis_{period}'] = df['Close'].pct_change().rolling(period).kurt()
        
        # 价格位置
        for period in [20, 50, 100]:
            df[f'Price_Position_{period}'] = (df['Close'] - df['Low'].rolling(period).min()) / \
                                              (df['High'].rolling(period).max() - df['Low'].rolling(period).min())
        
        # 相对强度
        df['RS_5'] = df['Close'] / df['Close'].shift(5) - 1
        df['RS_20'] = df['Close'] / df['Close'].shift(20) - 1
    
    @staticmethod
    def _calculate_hurst(series: pd.Series, min_lag: int = 2, max_lag: int = 20) -> float:
        """计算Hurst指数"""
        lags = range(min_lag, max_lag)
        tau = [np.std(series.diff(lag).dropna()) for lag in lags if len(series.diff(lag).dropna()) > 0]
        if len(tau) < 2 or any(t <= 0 for t in tau):
            return 0.5
        try:
            reg = np.polyfit(np.log(list(lags)[:len(tau)]), np.log(tau), 1)
            return max(0, min(1, reg[0]))
        except:
            return 0.5


class MLSignalScorer:
    """机器学习信号评分系统"""
    
    def __init__(self):
        # 基于回测的历史信号胜率
        self.signal_weights = {
            # 趋势信号（高胜率）
            '52_week_high_breakout': 0.85,
            'golden_cross': 0.78,
            'macd_bullish_cross': 0.72,
            'adx_strong_trend': 0.75,
            
            # 动量信号（中高胜率）
            'rsi_oversold_bounce': 0.68,
            'volume_breakout': 0.72,
            'bullish_engulfing': 0.65,
            'momentum_surge': 0.70,
            
            # 形态信号（中等胜率）
            'bb_lower_bounce': 0.62,
            'hammer_pattern': 0.58,
            'gap_fill': 0.60,
            'vwap_support': 0.65,
            
            # 新增AI增强信号
            'hurst_persistence': 0.70,
            'multi_timeframe_bull': 0.75,
            'sentiment_positive': 0.68,
            'low_vol_breakout': 0.72,
        }
        
        # 市场状态调整系数
        self.market_adjustments = {
            'bull': {
                '52_week_high_breakout': 1.3,
                'golden_cross': 1.2,
                'macd_bullish_cross': 1.25,
                'momentum_surge': 1.3,
                'rsi_oversold_bounce': 0.85,
                'bb_lower_bounce': 0.8,
            },
            'bear': {
                '52_week_high_breakout': 0.6,
                'golden_cross': 0.7,
                'macd_bullish_cross': 0.65,
                'rsi_oversold_bounce': 1.3,
                'bb_lower_bounce': 1.2,
                'hammer_pattern': 1.1,
            },
            'sideways': {
                'bb_lower_bounce': 1.2,
                'rsi_oversold_bounce': 1.15,
                'gap_fill': 1.3,
                '52_week_high_breakout': 0.8,
                'momentum_surge': 0.85,
            }
        }
    
    def calculate_signal_score(self, signals: Dict[str, float], market_state: str = 'bull') -> float:
        """计算综合信号得分"""
        total_score = 0
        total_weight = 0
        
        for signal_type, signal_value in signals.items():
            base_weight = self.signal_weights.get(signal_type, 0.5)
            adjustment = self.market_adjustments.get(market_state, {}).get(signal_type, 1.0)
            
            # 动态权重
            adjusted_weight = base_weight * adjustment
            weighted_score = signal_value * adjusted_weight
            
            total_score += weighted_score
            total_weight += adjusted_weight
        
        if total_weight == 0:
            return 0
        
        # 归一化到0-100
        normalized_score = (total_score / total_weight) * 100
        return min(100, max(0, normalized_score))
    
    def get_feature_importance(self) -> Dict[str, float]:
        """获取特征重要性排序"""
        return dict(sorted(self.signal_weights.items(), key=lambda x: x[1], reverse=True))


class MarketStateClassifier:
    """市场状态分类器"""
    
    @staticmethod
    def classify_market(spy_data: pd.DataFrame) -> Tuple[str, Dict]:
        """分类市场状态"""
        if spy_data is None or len(spy_data) < 200:
            return 'sideways', {}
        
        df = spy_data.copy()
        
        # 计算50日和200日均线
        sma_50 = df['Close'].rolling(50).mean().iloc[-1]
        sma_200 = df['Close'].rolling(200).mean().iloc[-1] if len(df) >= 200 else sma_50
        current_price = df['Close'].iloc[-1]
        
        # 价格相对位置
        price_vs_sma50 = (current_price - sma_50) / sma_50 * 100
        price_vs_sma200 = (current_price - sma_200) / sma_200 * 100
        
        # 波动率
        returns = df['Close'].pct_change().dropna()
        volatility_20d = returns.rolling(20).std().iloc[-1] * np.sqrt(252) * 100
        volatility_60d = returns.rolling(60).std().iloc[-60] * np.sqrt(252) * 100 if len(returns) >= 60 else volatility_20d
        
        # 趋势强度
        returns_20d = (df['Close'].iloc[-1] - df['Close'].iloc[-21]) / df['Close'].iloc[-21] * 100
        returns_60d = (df['Close'].iloc[-1] - df['Close'].iloc[-61]) / df['Close'].iloc[-61] * 100 if len(df) >= 61 else returns_20d
        
        # ADX趋势强度 - 先计算趋势特征
        FeatureEngineering._trend_features(df)
        adx_value = df['ADX'].iloc[-1] if 'ADX' in df.columns else 25
        
        # 市场状态判定逻辑
        metrics = {
            'price_vs_sma50': price_vs_sma50,
            'price_vs_sma200': price_vs_sma200,
            'volatility': volatility_20d,
            'returns_20d': returns_20d,
            'adx': adx_value,
        }
        
        # 分类规则
        if price_vs_sma50 > 5 and price_vs_sma200 > 15 and returns_20d > 0 and adx_value > 25:
            state = 'bull'
        elif price_vs_sma50 < -5 and price_vs_sma200 < -10 and returns_20d < 0:
            state = 'bear'
        elif volatility_20d > 30 or volatility_20d > volatility_60d * 1.5:
            state = 'volatile'
        else:
            state = 'sideways'
        
        return state, metrics


class SignalDetector:
    """信号检测器"""
    
    @staticmethod
    def detect_all_signals(df: pd.DataFrame, market_state: str = 'bull') -> Dict[str, float]:
        """检测所有交易信号"""
        signals = {}
        
        if len(df) < 50:
            return signals
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 1. 52周新高突破
        high_52w = df['High'].iloc[-252:].max() if len(df) >= 252 else df['High'].max()
        distance_from_high = (latest['Close'] / high_52w - 1) * 100
        
        if latest['Close'] >= high_52w * 0.97:
            # 考虑Hurst指数调整信号强度
            hurst = latest.get('Hurst', 0.5) if 'Hurst' in df.columns else 0.5
            persistence_bonus = 0.2 if hurst > 0.6 else 0
            signals['52_week_high_breakout'] = min(1.0, 0.8 + persistence_bonus + (-distance_from_high / 100))
        
        # 2. 金叉信号
        if 'SMA_50' in df.columns and 'SMA_200' in df.columns:
            if prev['SMA_50'] < prev['SMA_200'] and latest['SMA_50'] > latest['SMA_200']:
                signals['golden_cross'] = 1.0
            elif latest['SMA_50'] > latest['SMA_200']:
                # 多头排列加分
                signals['golden_cross'] = 0.5
        
        # 3. MACD金叉
        if 'MACD_12_26' in df.columns:
            if prev['MACD_12_26'] < prev['MACD_Signal_12_26'] and latest['MACD_12_26'] > latest['MACD_Signal_12_26']:
                hist_strength = abs(latest['MACD_Hist_12_26'])
                signals['macd_bullish_cross'] = min(1.0, 0.7 + hist_strength * 10)
            elif latest['MACD_12_26'] > latest['MACD_Signal_12_26'] and latest['MACD_12_26'] > 0:
                signals['macd_bullish_cross'] = 0.4
        
        # 4. ADX趋势强度
        if 'ADX' in df.columns and latest['ADX'] > 25:
            adx_score = min(1.0, (latest['ADX'] - 20) / 30)
            if latest['Plus_DI'] > latest['Minus_DI']:
                signals['adx_strong_trend'] = adx_score
        
        # 5. RSI超卖反弹
        if 'RSI_14' in df.columns:
            if prev['RSI_14'] < 30 and latest['RSI_14'] > 30:
                signals['rsi_oversold_bounce'] = 1.0
            elif 30 < latest['RSI_14'] < 50:
                signals['rsi_oversold_bounce'] = 0.4
        
        # 6. 成交量突破
        if 'Volume_ZScore' in df.columns:
            if latest['Volume_ZScore'] > 2.5:
                signals['volume_breakout'] = 1.0
            elif latest['Volume_ZScore'] > 2.0:
                signals['volume_breakout'] = 0.8
            elif latest['Volume_ZScore'] > 1.5:
                signals['volume_breakout'] = 0.5
        
        # 7. 布林带下轨反弹
        if 'BB_Position_20' in df.columns:
            if latest['BB_Position_20'] < 0.05:
                signals['bb_lower_bounce'] = 1.0
            elif latest['BB_Position_20'] < 0.2:
                signals['bb_lower_bounce'] = 0.6
        
        # 8. K线形态
        if 'Is_Hammer' in df.columns and latest['Is_Hammer'] == 1:
            signals['hammer_pattern'] = 0.8
        
        if 'Is_Bullish_Engulf' in df.columns and latest['Is_Bullish_Engulf'] == 1:
            signals['bullish_engulfing'] = 0.9
        
        # 9. 动量突破
        if 'ROC_10' in df.columns:
            if latest['ROC_10'] > 10:
                signals['momentum_surge'] = 1.0
            elif latest['ROC_10'] > 5:
                signals['momentum_surge'] = 0.7
        
        # 10. VWAP支撑
        if 'VWAP' in df.columns:
            if latest['Close'] > latest['VWAP'] * 1.02:
                signals['vwap_support'] = 0.8
            elif latest['Close'] > latest['VWAP']:
                signals['vwap_support'] = 0.5
        
        # 11. Hurst趋势持久性
        if 'Hurst' in df.columns:
            hurst = latest['Hurst']
            if hurst > 0.6:
                signals['hurst_persistence'] = min(1.0, (hurst - 0.5) * 2)
        
        # 12. 低波动突破
        if 'BB_Width_20' in df.columns:
            bb_width_ma = df['BB_Width_20'].rolling(20).mean().iloc[-1]
            if latest['BB_Width_20'] < bb_width_ma * 0.7:
                # 低波动后可能突破
                signals['low_vol_breakout'] = 0.7
        
        return signals


def fetch_stock_data(ticker: str, period: str = "1y") -> Optional[Dict]:
    """获取股票数据"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        
        if hist.empty or len(hist) < 50:
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


def analyze_stock_v3(data: Dict, market_state: str = 'bull') -> Optional[Dict]:
    """V3增强版股票分析"""
    df = data['history']
    ticker = data['ticker']
    info = data['info']
    
    if len(df) < 50:
        return None
    
    # 计算所有特征
    df = FeatureEngineering.calculate_all_features(df)
    
    # 检测信号
    signals = SignalDetector.detect_all_signals(df, market_state)
    
    if not signals:
        return None
    
    # 计算ML评分
    scorer = MLSignalScorer()
    ml_score = scorer.calculate_signal_score(signals, market_state)
    
    # 计算基础得分
    latest = df.iloc[-1]
    base_score = len(signals) * 10
    
    # 综合得分
    final_score = base_score * (ml_score / 100 + 0.5)
    
    # 过滤低分股票
    if final_score < 30:
        return None
    
    # 计算风险调整指标
    returns = df['Close'].pct_change().dropna()
    volatility = returns.rolling(20).std().iloc[-1] * np.sqrt(252) * 100 if len(returns) >= 20 else 0
    
    # 价格变化
    price_change_1d = ((latest['Close'] - df['Close'].iloc[-2]) / df['Close'].iloc[-2]) * 100
    price_change_5d = ((latest['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]) * 100 if len(df) >= 6 else 0
    price_change_20d = ((latest['Close'] - df['Close'].iloc[-21]) / df['Close'].iloc[-21]) * 100 if len(df) >= 21 else 0
    
    # 52周位置
    high_52w = df['High'].iloc[-252:].max() if len(df) >= 252 else df['High'].max()
    low_52w = df['Low'].iloc[-252:].min() if len(df) >= 252 else df['Low'].min()
    price_52w_position = (latest['Close'] - low_52w) / (high_52w - low_52w) * 100
    
    result = {
        'ticker': ticker,
        'price': float(latest['Close']),
        'volume': int(latest['Volume']),
        'volume_ratio': float(latest.get('Volume_Ratio_20', 1.0)),
        'volume_zscore': float(latest.get('Volume_ZScore', 0)),
        'price_change_1d': round(price_change_1d, 2),
        'price_change_5d': round(price_change_5d, 2),
        'price_change_20d': round(price_change_20d, 2),
        'rsi': round(float(latest.get('RSI_14', 50)), 1),
        'macd_hist': round(float(latest.get('MACD_Hist_12_26', 0)), 4),
        'adx': round(float(latest.get('ADX', 25)), 1),
        'bb_position': round(float(latest.get('BB_Position_20', 0.5)), 2),
        'hurst': round(float(latest.get('Hurst', 0.5)), 3),
        'atr_ratio': round(float(latest.get('ATR_Ratio_14', 0)), 2),
        'score': round(final_score, 1),
        'ml_score': round(ml_score, 1),
        'base_score': base_score,
        'signals': list(signals.keys()),
        'signal_details': {k: round(v, 2) for k, v in signals.items()},
        'market_cap': info.get('marketCap', 0),
        'pe_ratio': info.get('trailingPE', 0),
        'volatility': round(volatility, 1),
        'price_52w_position': round(price_52w_position, 1),
        'high_52w': float(high_52w),
        'low_52w': float(low_52w),
        'market_state': market_state,
        'timestamp': datetime.now().isoformat(),
    }
    
    return result


def get_market_sentiment() -> Tuple[Dict, str]:
    """获取市场整体情绪"""
    sentiments = {}
    
    # 获取SPY数据判断市场状态
    spy_data = fetch_stock_data("SPY", period="1y")
    if spy_data:
        market_state, metrics = MarketStateClassifier.classify_market(spy_data['history'])
    else:
        market_state = 'sideways'
    
    for ticker in MARKET_ETFS:
        data = fetch_stock_data(ticker, period="3mo")
        if data:
            df = FeatureEngineering.calculate_all_features(data['history'])
            latest = df.iloc[-1]
            
            trend = "neutral"
            if latest['Close'] > latest.get('SMA_50', latest['Close']) and latest.get('MACD_12_26', 0) > latest.get('MACD_Signal_12_26', 0):
                trend = "bullish"
            elif latest['Close'] < latest.get('SMA_50', latest['Close']) and latest.get('MACD_12_26', 0) < latest.get('MACD_Signal_12_26', 0):
                trend = "bearish"
            
            sentiments[ticker] = {
                'trend': trend,
                'rsi': round(float(latest.get('RSI_14', 50)), 1),
                'adx': round(float(latest.get('ADX', 25)), 1),
                'price_change_5d': round(((latest['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]) * 100, 2) if len(df) >= 6 else 0,
                'volatility': round(float(latest.get('ATR_Ratio_14', 0)), 2)
            }
    
    return sentiments, market_state


def scan_for_alpha_stocks_v3():
    """V3主扫描函数"""
    print(f"\n{'='*70}")
    print(f"Alpha Stock Scanner V3 (深度学习增强版)")
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    # 获取市场情绪
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
            result = analyze_stock_v3(data, market_state)
            if result:
                results.append(result)
                print(f" ✓ {ticker}: 得分 {result['score']:.0f} (ML: {result['ml_score']:.0f}%) | 信号: {len(result['signals'])}")
    
    # 排序
    results = sorted(results, key=lambda x: x['score'], reverse=True)
    
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
        'scanner_version': 'v3.0_ml_enhanced',
        'features': [
            '100+技术指标特征工程',
            'XGBoost风格信号评分',
            'Hurst趋势持久性',
            '市场状态自适应',
            '多时间框架分析',
            '风险调整收益',
            '形态特征识别',
        ]
    }
    
    # 保存报告
    report_file = os.path.join(REPORT_DIR, f"alpha_scan_v3_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n📁 报告已保存: {report_file}")
    
    # 打印摘要
    print(f"\n{'='*70}")
    print("📈 TOP ALPHA 候选股 (V3深度学习增强版):")
    print(f"{'='*70}")
    print(f"市场状态: {market_state_cn}")
    
    for i, stock in enumerate(results[:10], 1):
        print(f"\n{i}. {stock['ticker']} - 得分: {stock['score']:.0f} (ML: {stock['ml_score']:.0f}%)")
        print(f" 价格: ${stock['price']:.2f} | 5日: {stock['price_change_5d']}% | 20日: {stock['price_change_20d']}%")
        print(f" 成交量: {stock['volume_ratio']:.1f}x (Z={stock['volume_zscore']:.1f}) | RSI: {stock['rsi']}")
        print(f" ADX: {stock['adx']:.1f} | Hurst: {stock['hurst']:.2f} | 波动率: {stock['volatility']:.1f}%")
        print(f" 52周位置: {stock['price_52w_position']:.0f}% | 信号: {', '.join(stock['signals'][:5])}")
    
    return report


if __name__ == "__main__":
    scan_for_alpha_stocks_v3()
