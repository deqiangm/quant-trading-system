#!/usr/bin/env python3
"""
Alpha Stock Scanner V4 - Social Sentiment + TV + LLM + Insider Enhanced

V4 enhancements over V3:
- Reddit WSB mention tracking + sentiment analysis
- Multi-source sentiment aggregation (Reddit, Finviz, StockTwits)
- Mention spike detection (unusual social activity)
- Call/Put ratio from social media signals
- Social-technical fusion scoring system
- Dynamic weight adjustment based on market regime

V5 enhancements (integrated into V4):
- TradingView Screener data: consensus, fundamentals, advanced indicators
- LLM Sentiment: DeepSeek V4 Flash replaces VADER for financial text
- SEC Form 4 Insider Trading: cluster buying detection
- 4-dimension fusion: tech + social + tv + insider
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
import logging
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

# Import V3 components
from alpha_scanner_v3 import (
    FeatureEngineering, MLSignalScorer, MarketStateClassifier,
    SignalDetector, fetch_stock_data, MARKET_STATES, MARKET_ETFS
)

# Import V4 social sentiment module
from social_sentiment import (
    SocialSentimentEngine, TickerExtractor, SocialSentimentAnalyzer
)

# Import V5 enhancement modules
from tv_screener import TradingViewDataFetcher
from llm_sentiment import LLMSentimentAnalyzer
from insider_trading import InsiderTradingFetcher

# Import V6 crash warning module
from crash_warning import CrashWarningSystem

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(BASE_DIR, "reports")
HTML_DIR = os.path.join(BASE_DIR, "html_reports")
os.makedirs(REPORT_DIR, exist_ok=True)
os.makedirs(HTML_DIR, exist_ok=True)

# Extended ticker pool for V4 (includes WSB favorites)
V4_TICKERS = [
    # Tech giants
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    # Semiconductors
    "AMD", "INTC", "QCOM", "AVGO", "TXN", "NXPI", "MU", "AMAT", "LRCX", "KLAC",
    "MRVL", "ON", "MCHP", "SWKS", "ENPH", "SEDG",
    # Software
    "CRM", "ORCL", "ADBE", "NOW", "SNOW", "PLTR", "MDB",
    # Fintech
    "V", "MA", "PYPL", "SQ", "COIN", "HOOD", "SOFI",
    # Streaming / Media
    "NFLX", "DIS", "SPOT",
    # AI theme
    "SMCI", "ARM", "AI", "SOUN", "BBAI", "RKLB", "IONQ", "RGTI", "QBTS",
    # Meme / WSB favorites
    "GME", "AMC", "BB", "RIVN", "LCID", "NIO",
    # Other hot
    "RDDT", "DDOG", "ZS", "CRWD", "SSTK", "WDC", "STX",
    # Chinese ADR
    "BABA", "JD", "PDD", "BIDU",
    # Crypto adjacent
    "MSTR", "RIOT", "CLSK", "MARA",
]


class SocialTechnicalFusionScorer:
    """5-dimension fusion scoring system: tech + social + tv + insider + crash_warning.

    The fusion formula:
    final_score = w_tech * tech_score + w_social * social_score
    + w_tv * tv_score + w_insider * insider_score

    Crash warning acts as a MACRO OVERLAY — it doesn't add a 5th weight,
    but instead MODIFIES the final score based on market-wide risk:
    - High crash warning (>70): applies risk discount to all long candidates
    - Medium crash warning (30-70): reduces tech weight, increases defensive signal weight
    - Low crash warning (<30): no modification

    Weights adapt dynamically based on:
    - Market regime (social signals matter more in speculative markets)
    - Social mention volume (high volume = higher social weight)
    - TV data availability (TV fundamentals boost confidence)
    - Insider signal strength (cluster buying = strong signal)
    - Crash warning level (high risk = discount long positions)
    """

    # Base weights (4 dimensions — crash warning is overlay)
    TECHNICAL_BASE_WEIGHT = 0.45
    SOCIAL_BASE_WEIGHT = 0.30
    TV_BASE_WEIGHT = 0.15
    INSIDER_BASE_WEIGHT = 0.10

    # Market-regime social weight adjustments
    MARKET_SOCIAL_ADJUSTMENTS = {
        'bull': 1.2,  # Social hype amplifies in bull markets
        'bear': 0.8,  # Social panic can be misleading in bears
        'sideways': 1.0,  # Neutral
        'volatile': 1.3,  # Social signals critical in volatility
    }

    # Social signal thresholds
    MENTION_SPIKE_THRESHOLD = 2.5  # 2.5x average = spike
    HIGH_MENTION_THRESHOLD = 5  # 5+ mentions = significant
    SOCIAL_SIGNAL_BULL_THRESHOLD = 70
    SOCIAL_SIGNAL_BEAR_THRESHOLD = 30

    def calculate_fusion_score(
        self,
        technical_score: float,
        social_data: Dict,
        tv_data: Dict = None,
        insider_data: Dict = None,
        market_state: str = 'sideways',
        crash_warning: Dict = None,
    ) -> Dict:
        """Calculate fused multi-dimension score with crash warning overlay."""
        social_signal = social_data.get('social_signal', 50)

        # === Dynamic weight calculation ===
        social_weight = self.SOCIAL_BASE_WEIGHT
        tech_weight = self.TECHNICAL_BASE_WEIGHT
        tv_weight = self.TV_BASE_WEIGHT
        insider_weight = self.INSIDER_BASE_WEIGHT

        # Market regime adjustment (affects social weight)
        regime_adj = self.MARKET_SOCIAL_ADJUSTMENTS.get(market_state, 1.0)
        social_weight *= regime_adj

        # Mention spike boost
        spike_ratio = social_data.get('mention_spike_ratio', 1.0)
        if spike_ratio >= self.MENTION_SPIKE_THRESHOLD:
            spike_boost = min(0.15, (spike_ratio - 1) * 0.05)
            social_weight += spike_boost

        # High mention volume boost
        mention_count = social_data.get('wsb_mention_count', 0)
        if mention_count >= self.HIGH_MENTION_THRESHOLD:
            social_weight += 0.05

        # TV data availability: redistribute weight if no TV data
        tv_available = tv_data is not None and len(tv_data) > 0
        if not tv_available:
            tv_weight = 0
            # Redistribute TV weight proportionally to other dimensions
            tech_weight += self.TV_BASE_WEIGHT * 0.5
            social_weight += self.TV_BASE_WEIGHT * 0.3
            insider_weight += self.TV_BASE_WEIGHT * 0.2

        # Insider signal strength: boost if cluster buying detected
        insider_signal_strength = 0
        insider_available = insider_data is not None and insider_data.get('signal') != 'neutral'
        if insider_available:
            insider_score_abs = abs(insider_data.get('score', 0))
            insider_signal_strength = insider_score_abs
            # Strong insider signal (>=50) gets weight boost
            if insider_score_abs >= 50:
                insider_weight += 0.05
                social_weight -= 0.03
                tv_weight -= 0.02
            else:
                insider_weight = 0
                # Redistribute insider weight
                tech_weight += self.INSIDER_BASE_WEIGHT * 0.5
                social_weight += self.INSIDER_BASE_WEIGHT * 0.3
                tv_weight += self.INSIDER_BASE_WEIGHT * 0.2
        else:
            insider_weight = 0
            # Redistribute insider weight
            tech_weight += self.INSIDER_BASE_WEIGHT * 0.5
            social_weight += self.INSIDER_BASE_WEIGHT * 0.3
            tv_weight += self.INSIDER_BASE_WEIGHT * 0.2

        # === Crash Warning Overlay ===
        crash_discount = 1.0  # No discount by default
        crash_level = 'NORMAL'
        crash_score = 0
        crash_signals = []
        if crash_warning:
            crash_score = crash_warning.get('composite_score', 0)
            crash_level = crash_warning.get('warning_level', '✅ NORMAL')
            crash_signals = crash_warning.get('all_signals', [])

            if crash_score >= 70:
                # CRASH WARNING: heavy discount on long positions
                crash_discount = 0.60  # 40% discount
                # Shift weights: reduce tech (momentum), increase social (sentiment)
                tech_weight *= 0.7
                social_weight *= 1.2
            elif crash_score >= 50:
                # ELEVATED RISK: moderate discount
                crash_discount = 0.80  # 20% discount
                tech_weight *= 0.85
            elif crash_score >= 30:
                # CAUTION: slight discount
                crash_discount = 0.92  # 8% discount

        # Normalize weights to sum to 1
        total_weight = tech_weight + social_weight + tv_weight + insider_weight
        if total_weight > 0:
            tech_weight /= total_weight
            social_weight /= total_weight
            tv_weight /= total_weight
            insider_weight /= total_weight

        # === Calculate dimension scores ===

        # Technical score: normalize from V3 scale to 0-100
        tech_normalized = min(100, max(0, technical_score * 1.5))

        # Social score: already 0-100
        social_score = social_signal

        # TV score: combination of fundamentals + technical enhancement
        tv_fundamentals = 50.0
        tv_technical = 50.0
        tv_score = 50.0
        tv_consensus_label = 'unknown'
        if tv_available:
            tv_fundamentals = TradingViewDataFetcher.get_fundamentals_score(tv_data)
            tv_technical = TradingViewDataFetcher.get_technical_enhancement_score(tv_data)
            tv_consensus_label = TradingViewDataFetcher.get_consensus_signal(tv_data.get('recommend_all', 0))
            # Weight: 40% fundamentals + 60% technical (TV technical has more signal value)
            tv_score = tv_fundamentals * 0.4 + tv_technical * 0.6

        # Insider score: map from [-100, +100] to [0, 100]
        insider_score_raw = 50.0  # neutral
        if insider_available:
            insider_score_raw = 50 + insider_data.get('score', 0) * 0.5

        # === Fusion ===
        fused_score = (
            tech_weight * tech_normalized +
            social_weight * social_score +
            tv_weight * tv_score +
            insider_weight * insider_score_raw
        )

        # === Apply Crash Warning Discount ===
        fused_score *= crash_discount

        # Divergence detection (tech vs social disagreement)
        divergence = abs(tech_normalized - social_signal)
        divergence_label = "aligned"
        if divergence > 40:
            divergence_label = "high_divergence"
            fused_score *= 0.9  # Slight penalty
        elif divergence > 25:
            divergence_label = "moderate_divergence"

        # Social conviction flag
        social_conviction = None
        if social_signal >= self.SOCIAL_SIGNAL_BULL_THRESHOLD and mention_count >= 3:
            social_conviction = "strong_bullish"
        elif social_signal >= 60 and mention_count >= 2:
            social_conviction = "moderate_bullish"
        elif social_signal <= self.SOCIAL_SIGNAL_BEAR_THRESHOLD and mention_count >= 3:
            social_conviction = "strong_bearish"

        # Call/Put ratio signal
        cp_signal = "neutral"
        calls = social_data.get('call_count', 0)
        puts = social_data.get('put_count', 0)
        if calls + puts >= 2:
            cp_ratio = calls / (calls + puts)
            if cp_ratio >= 0.75:
                cp_signal = "heavy_calls"
            elif cp_ratio >= 0.6:
                cp_signal = "call_bias"
            elif cp_ratio <= 0.25:
                cp_signal = "heavy_puts"
            elif cp_ratio <= 0.4:
                cp_signal = "put_bias"

        return {
            'fused_score': round(fused_score, 1),
            'technical_component': round(tech_weight * tech_normalized, 1),
            'social_component': round(social_weight * social_score, 1),
            'tv_component': round(tv_weight * tv_score, 1),
            'insider_component': round(insider_weight * insider_score_raw, 1),
            'tech_weight': round(tech_weight, 3),
            'social_weight': round(social_weight, 3),
            'tv_weight': round(tv_weight, 3),
            'insider_weight': round(insider_weight, 3),
            'tech_normalized': round(tech_normalized, 1),
            'social_signal': social_signal,
            'tv_fundamentals': round(tv_fundamentals, 1),
            'tv_technical': round(tv_technical, 1),
            'tv_score': round(tv_score, 1),
            'tv_consensus': tv_consensus_label,
            'insider_signal': insider_data.get('signal', 'neutral') if insider_data else 'unavailable',
            'insider_score_raw': insider_data.get('score', 0) if insider_data else 0,
            'insider_score': round(insider_score_raw, 1),
            'divergence': round(divergence, 1),
            'divergence_label': divergence_label,
            'social_conviction': social_conviction,
            'cp_signal': cp_signal,
        'wsb_mention_count': mention_count,
        'mention_spike_ratio': spike_ratio,
        # Crash warning overlay
        'crash_discount': round(crash_discount, 2),
        'crash_warning_score': crash_score,
        'crash_warning_level': crash_level,
    }


def analyze_stock_v4(
    data: Dict,
    market_state: str = 'bull',
    social_data: Dict = None,
    tv_data: Dict = None,
    insider_data: Dict = None,
    crash_warning: Dict = None,
) -> Optional[Dict]:
    """V4 enhanced stock analysis with all dimension integration + crash warning."""
    df = data['history']
    ticker = data['ticker']
    info = data['info']

    if len(df) < 50:
        return None

    # === Technical Analysis (from V3) ===
    df = FeatureEngineering.calculate_all_features(df)
    signals = SignalDetector.detect_all_signals(df, market_state)

    if not signals:
        return None

    # ML technical score (from V3)
    scorer = MLSignalScorer()
    ml_score = scorer.calculate_signal_score(signals, market_state)
    base_score = len(signals) * 10
    technical_score = base_score * (ml_score / 100 + 0.5)

    if technical_score < 20:
        return None

    # === Social Sentiment Analysis (V4) ===
    if social_data is None:
        social_data = {
            'social_signal': 50,
            'wsb_mention_count': 0,
            'mention_spike_ratio': 1.0,
            'wsb_sentiment': 0,
            'call_count': 0,
            'put_count': 0,
            'sources_available': [],
        }

    # === 4-Dimension Fusion Scoring ===
    fusion = SocialTechnicalFusionScorer()
    fusion_result = fusion.calculate_fusion_score(
        technical_score, social_data, tv_data, insider_data, market_state,
        crash_warning=crash_warning
    )

    # Filter low fused scores
    if fusion_result['fused_score'] < 25:
        return None

    # Price data
    latest = df.iloc[-1]
    price_change_1d = ((latest['Close'] - df['Close'].iloc[-2]) / df['Close'].iloc[-2]) * 100
    price_change_5d = ((latest['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]) * 100 if len(df) >= 6 else 0
    price_change_20d = ((latest['Close'] - df['Close'].iloc[-21]) / df['Close'].iloc[-21]) * 100 if len(df) >= 21 else 0

    # 52-week position
    high_52w = df['High'].iloc[-252:].max() if len(df) >= 252 else df['High'].max()
    low_52w = df['Low'].iloc[-252:].min() if len(df) >= 252 else df['Low'].min()
    price_52w_position = (latest['Close'] - low_52w) / (high_52w - low_52w) * 100

    # Volatility
    returns = df['Close'].pct_change().dropna()
    volatility = returns.rolling(20).std().iloc[-1] * np.sqrt(252) * 100 if len(returns) >= 20 else 0

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

        # V3 scores
        'technical_score': round(technical_score, 1),
        'ml_score': round(ml_score, 1),
        'base_score': base_score,

        # V4 social data
        'social_signal': social_data.get('social_signal', 50),
        'wsb_mentions': social_data.get('wsb_mention_count', 0),
        'wsb_sentiment': social_data.get('wsb_sentiment', 0),
        'mention_spike_ratio': social_data.get('mention_spike_ratio', 1.0),
        'cp_signal': fusion_result.get('cp_signal', 'neutral'),
        'social_conviction': fusion_result.get('social_conviction'),

        # V5 TV data
        'tv_fundamentals': fusion_result.get('tv_fundamentals', 50),
        'tv_technical': fusion_result.get('tv_technical', 50),
        'tv_score': fusion_result.get('tv_score', 50),
        'tv_consensus': fusion_result.get('tv_consensus', 'unknown'),

        # V5 Insider data
        'insider_signal': fusion_result.get('insider_signal', 'unavailable'),
        'insider_score': fusion_result.get('insider_score', 50),
        'insider_buys': insider_data.get('details', {}).get('buy_count', 0) if insider_data else 0,
        'insider_sells': insider_data.get('details', {}).get('sell_count', 0) if insider_data else 0,

        # V4 fusion
        'fused_score': fusion_result['fused_score'],
        'tech_weight': fusion_result['tech_weight'],
        'social_weight': fusion_result['social_weight'],
        'tv_weight': fusion_result.get('tv_weight', 0),
        'insider_weight': fusion_result.get('insider_weight', 0),
        'divergence': fusion_result['divergence'],
        'divergence_label': fusion_result['divergence_label'],

        # V6 Crash Warning
        'crash_discount': fusion_result.get('crash_discount', 1.0),
        'crash_warning_score': fusion_result.get('crash_warning_score', 0),
        'crash_warning_level': fusion_result.get('crash_warning_level', 'NORMAL'),

        # Traditional fields
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


def scan_for_alpha_stocks_v4(social_limit: int = 25):
    """V4 main scan: technical + social + TV + LLM sentiment + insider fusion."""
    print(f"\n{'='*70}")
    print(f"Alpha Stock Scanner V4+ (Multi-Dimension Fusion)")
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    # === Phase 1: Social Sentiment Data Collection ===
    print("Phase 1: Collecting social sentiment data...")
    social_engine = SocialSentimentEngine()

    # Initialize LLM sentiment analyzer (enhances social analysis)
    llm_analyzer = None
    try:
        llm_analyzer = LLMSentimentAnalyzer()
        if llm_analyzer.is_llm_available:
            print(" LLM Sentiment: DeepSeek V4 Flash available")
        else:
            print(" LLM Sentiment: not available, using VADER fallback")
            llm_analyzer = None
    except Exception as e:
        print(f" LLM Sentiment: init failed ({e}), using VADER fallback")
        llm_analyzer = None

    try:
        fetch_result = social_engine.fetch_wsb_data(limit_per_subreddit=social_limit)
        print(f" Reddit: {fetch_result['total_posts']} posts from {len(fetch_result['per_subreddit'])} subreddits")
        for sub, count in fetch_result['per_subreddit'].items():
            if count > 0:
                print(f"  r/{sub}: {count} posts")
    except Exception as e:
        logger.error(f"Social data fetch failed: {e}")
        fetch_result = {'total_posts': 0, 'per_subreddit': {}}

    # Get top mentioned tickers from Reddit
    top_social_tickers = social_engine.data_store.get_daily_top_tickers(limit=30)
    social_ticker_set = {t['ticker'] for t in top_social_tickers}
    print(f" Top social tickers: {', '.join(list(social_ticker_set)[:15])}")

    # Mention spikes
    spikes = social_engine.data_store.detect_mention_spikes(threshold=2.5, min_mentions=2)
    if spikes:
        spike_strs = [f"{s['ticker']}({s['spike_ratio']}x)" for s in spikes[:5]]
        print(f" Mention spikes: {', '.join(spike_strs)}")

    # === Phase 2: TradingView Data Collection ===
    print("\nPhase 2: Fetching TradingView data...")
    tv_fetcher = TradingViewDataFetcher()
    scan_tickers = list(dict.fromkeys(V4_TICKERS + list(social_ticker_set)))
    try:
        tv_data_cache = tv_fetcher.fetch_ticker_data(scan_tickers)
        tv_ticker_count = len([k for k, v in tv_data_cache.items() if v and v.get('close')])
        print(f" TradingView: {tv_ticker_count}/{len(scan_tickers)} tickers with data")
    except Exception as e:
        logger.error(f"TV data fetch failed: {e}")
        tv_data_cache = {}
        print(f" TradingView: failed ({e}), using yfinance fallback")

    # === Phase 3: Insider Trading Data Collection ===
    print("\nPhase 3: Fetching insider trading data...")
    insider_fetcher = None
    insider_signals_cache = {}
    try:
        insider_fetcher = InsiderTradingFetcher(ticker_pool=scan_tickers)
        recent_filings = insider_fetcher.fetch_recent_filings(hours=168)  # 7 days
        matched_filings = [f for f in recent_filings if f.get('ticker')]
        print(f" SEC Form 4: {len(recent_filings)} filings, {len(matched_filings)} matched to tickers")

        # Get insider signals for matched tickers
        if matched_filings:
            matched_tickers = list(set(f['ticker'] for f in matched_filings if f['ticker']))
            for t in matched_tickers[:20]:  # Limit to avoid too many API calls
                try:
                    signal = insider_fetcher.get_insider_signal(t)
                    if signal.get('signal') != 'neutral':
                        insider_signals_cache[t] = signal
                except Exception:
                    pass
            if insider_signals_cache:
                insider_strs = [f"{t}={s['signal']}({s['score']:+.0f})" for t, s in insider_signals_cache.items()]
                print(f" Insider signals: {', '.join(insider_strs[:5])}")
    except Exception as e:
        logger.error(f"Insider trading fetch failed: {e}")
        print(f" SEC Form 4: failed ({e})")

    # === Phase 4: Market State Analysis ===
    print("\nPhase 4: Analyzing market state...")
    spy_data = fetch_stock_data("SPY", period="1y")
    if spy_data:
        market_state, metrics = MarketStateClassifier.classify_market(spy_data['history'])
    else:
        market_state = 'sideways'
        metrics = {}
    market_state_cn = MARKET_STATES.get(market_state, market_state)
    print(f" Market state: {market_state_cn} ({market_state})")
    if metrics:
        print(f" SPY vs SMA50: {metrics.get('price_vs_sma50', 0):+.1f}% | Vol: {metrics.get('volatility', 0):.1f}%")

    # Market sentiment from ETFs
    market_sentiment = {}
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
            market_sentiment[ticker] = {
                'trend': trend,
                'rsi': round(float(latest.get('RSI_14', 50)), 1),
                'adx': round(float(latest.get('ADX', 25)), 1),
                'price_change_5d': round(((latest['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]) * 100, 2) if len(df) >= 6 else 0,
                'volatility': round(float(latest.get('ATR_Ratio_14', 0)), 2),
            }
        emoji = "\U0001f7e2" if trend == "bullish" else "\U0001f534" if trend == "bearish" else "\U0001f7e1"
        print(f" {ticker}: {emoji} {trend} | RSI:{market_sentiment[ticker]['rsi']} | 5D:{market_sentiment[ticker]['price_change_5d']:+.1f}%")

    # === Phase 4.5: Crash Warning Analysis ===
    print("\nPhase 4.5: Running 5-layer crash warning analysis...")
    crash_warning_result = None
    try:
        crash_system = CrashWarningSystem(tickers=scan_tickers)
        crash_warning_result = crash_system.run_analysis()
        cw_score = crash_warning_result['composite_score']
        cw_level = crash_warning_result['warning_level']
        cw_active = crash_warning_result['active_layers']
        print(f" Crash Warning: {cw_level} ({cw_score}/100, {cw_active}/5 layers active)")
        if crash_warning_result.get('all_signals'):
            for sig in crash_warning_result['all_signals'][:5]:
                print(f"   ⚠️  {sig}")
    except Exception as e:
        logger.error(f"Crash warning analysis failed: {e}")
        print(f" Crash Warning: analysis failed ({e})")

    # === Phase 5: Multi-Dimension Fusion Scan ===
    print(f"\nPhase 5: Scanning {len(scan_tickers)} tickers (4-dimension fusion)...")

    # Pre-fetch social scores for all tickers
    print(" Pre-fetching social scores...")
    social_scores_cache = {}
    for i, ticker in enumerate(scan_tickers):
        if i % 20 == 0 and i > 0:
            print(f"  Social progress: {i}/{len(scan_tickers)}")
        try:
            score_data = social_engine.get_ticker_social_score(ticker)

            # If LLM analyzer is available, enhance social scores with LLM
            if llm_analyzer and score_data.get('wsb_mention_count', 0) >= 1:
                try:
                    # Get recent posts for this ticker
                    posts = social_engine.data_store.get_posts_by_ticker(ticker, limit=10)
                    if posts:
                        llm_result = llm_analyzer.get_enhanced_sentiment(posts)
                        if llm_result.get('llm_available'):
                            score_data['social_signal'] = llm_result.get('composite_score', score_data['social_signal'])
                            score_data['llm_signal'] = llm_result.get('signal_label', 'neutral')
                            score_data['llm_avg_score'] = llm_result.get('avg_score', 0)
                except Exception as e:
                    logger.debug(f"LLM enhancement failed for {ticker}: {e}")

            social_scores_cache[ticker] = score_data
        except Exception:
            social_scores_cache[ticker] = {
                'social_signal': 50, 'wsb_mention_count': 0,
                'mention_spike_ratio': 1.0, 'wsb_sentiment': 0,
                'call_count': 0, 'put_count': 0, 'sources_available': [],
            }

    # Technical scan
    print(" Running technical + fusion analysis...")
    results = []
    for i, ticker in enumerate(scan_tickers):
        if i % 10 == 0:
            print(f"  Progress: {i}/{len(scan_tickers)}")

        data = fetch_stock_data(ticker)
        if not data:
            # Social-only tickers (no yfinance data or too few bars)
            social = social_scores_cache.get(ticker, {})
            if social.get('social_signal', 50) >= 70 and social.get('wsb_mention_count', 0) >= 3:
                results.append({
                    'ticker': ticker,
                    'price': 0,
                    'fused_score': social['social_signal'] * 0.4,  # Discount without technical
                    'technical_score': 0,
                    'social_signal': social['social_signal'],
                    'wsb_mentions': social.get('wsb_mention_count', 0),
                    'wsb_sentiment': social.get('wsb_sentiment', 0),
                    'mention_spike_ratio': social.get('mention_spike_ratio', 1.0),
                    'divergence_label': 'social_only',
                    'social_conviction': None,
                    'cp_signal': 'neutral',
                    'tv_score': 50, 'tv_consensus': 'unknown',
                    'insider_signal': 'unavailable', 'insider_score': 50,
                    'signals': ['social_hype'],
                    'market_state': market_state,
                    'timestamp': datetime.now().isoformat(),
                })
            continue

        social = social_scores_cache.get(ticker, {})
        tv = tv_data_cache.get(ticker)
        insider = insider_signals_cache.get(ticker)
        try:
            result = analyze_stock_v4(data, market_state, social, tv, insider, crash_warning=crash_warning_result)
        except Exception as e:
            logging.warning(f"analyze_stock_v4 failed for {ticker}: {e}")
            result = None
        if result:
            results.append(result)
            signals_short = ', '.join(result['signals'][:3])
            div = f"div:{result['divergence_label'][:4]}" if result['divergence_label'] != 'aligned' else ""
            tv_label = f"TV:{result.get('tv_consensus', '?')[:2]}" if result.get('tv_consensus', 'unknown') != 'unknown' else ""
            ins_label = f"INS:{result.get('insider_signal', '?')[:3]}" if result.get('insider_signal', 'unavailable') != 'unavailable' else ""
            cw_label = f"CW:{result.get('crash_warning_score', 0)}" if result.get('crash_warning_score', 0) > 0 else ""
            extras = ' '.join(filter(None, [div, tv_label, ins_label, cw_label]))
            print(f"  \u2713 {ticker}: fused={result['fused_score']:.0f} (tech={result['technical_score']:.0f} soc={result['social_signal']:.0f} tv={result.get('tv_score',50):.0f}) | {signals_short} {extras}")

    # Sort by fused score
    results = sorted(results, key=lambda x: x.get('fused_score', 0), reverse=True)

    # === Phase 6: Generate Report ===
    report = {
        'timestamp': datetime.now().isoformat(),
    'scanner_version': 'v4.2_crash_warning_fusion',
    'market_sentiment': market_sentiment,
    'market_state': market_state,
    'market_state_cn': market_state_cn,
    'crash_warning': crash_warning_result,  # V6 crash warning overlay
    'total_scanned': len(scan_tickers),
        'alpha_candidates': len(results),
        'social_posts_fetched': fetch_result.get('total_posts', 0),
        'social_subreddits': fetch_result.get('per_subreddit', {}),
        'mention_spikes': spikes,
        'insider_filings_found': len(recent_filings) if insider_fetcher else 0,
        'insider_signals_count': len(insider_signals_cache),
        'tv_tickers_with_data': len([k for k, v in tv_data_cache.items() if v and v.get('close')]),
        'llm_sentiment_available': llm_analyzer is not None,
        'top_picks': results[:20],
        'all_candidates': results,
        'features': [
            'V3 technical indicators (100+)',
            'ML signal scoring (XGBoost-style)',
            'Reddit WSB sentiment analysis (VADER + LLM)',
            'Multi-source sentiment (Finviz)',
            'Mention spike detection',
            'Call/Put ratio from social signals',
            'TradingView consensus + fundamentals + advanced indicators',
            'SEC Form 4 insider trading signals',
            'LLM financial sentiment (DeepSeek V4 Flash)',
        '4-dimension fusion scoring (tech + social + tv + insider)',
        '5-layer crash warning system (euphoria + yield curve + credit + systemic + technical)',
        'Crash warning overlay (risk discount on long positions)',
        'Divergence detection (tech vs social)',
            'Dynamic weight by market regime',
        ],
    }

    # Save report
    report_file = os.path.join(REPORT_DIR, f"alpha_scan_v4_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved: {report_file}")

    # Print summary
    print(f"\n{'='*70}")
    print("TOP ALPHA CANDIDATES (V4+ Multi-Dimension Fusion):")
    print(f"{'='*70}")
    print(f"Market: {market_state_cn} | Candidates: {len(results)}/{len(scan_tickers)}")
    print(f"Dimensions: Tech + Social + TV + Insider")

    for i, stock in enumerate(results[:12], 1):
        fused = stock.get('fused_score', 0)
        tech = stock.get('technical_score', 0)
        soc = stock.get('social_signal', 50)
        tv = stock.get('tv_score', 50)
        ins = stock.get('insider_score', 50)
        mentions = stock.get('wsb_mentions', 0)
        wsb = stock.get('wsb_sentiment', 0)
        div = stock.get('divergence_label', 'aligned')
        conviction = stock.get('social_conviction', '')
        cp = stock.get('cp_signal', 'neutral')
        tv_cons = stock.get('tv_consensus', 'unknown')
        ins_sig = stock.get('insider_signal', 'unavailable')

        print(f"\n{i}. {stock['ticker']} - Fused: {fused:.0f} (Tech:{tech:.0f} Soc:{soc:.0f} TV:{tv:.0f} Ins:{ins:.0f})")
        if stock.get('price', 0) > 0:
            print(f"   Price: ${stock['price']:.2f} | 5D: {stock.get('price_change_5d',0):+.1f}% | RSI: {stock.get('rsi',0)}")
        print(f"   WSB: {mentions} mentions (sent:{wsb:.2f}) | C/P: {cp}")
        if tv_cons != 'unknown':
            print(f"   TV: {tv_cons} | Fundamentals: {stock.get('tv_fundamentals',50):.0f} | Tech+: {stock.get('tv_technical',50):.0f}")
        if ins_sig != 'unavailable':
            buys = stock.get('insider_buys', 0)
            sells = stock.get('insider_sells', 0)
            print(f"   INSIDER: {ins_sig} (buys:{buys} sells:{sells})")
        if div != 'aligned':
            print(f"   DIVERGENCE: {div}")
        if conviction:
            print(f"   SOCIAL CONVICTION: {conviction}")

    # Generate HTML report
    try:
        from generate_v4_report import generate_v4_report, save_html_report
        html_content = generate_v4_report(report)
        html_path = save_html_report(html_content)
        print(f"\nHTML report: {html_path}")
    except Exception as e:
        print(f"\nHTML report generation failed: {e}")

    return report


if __name__ == "__main__":
    scan_for_alpha_stocks_v4()
