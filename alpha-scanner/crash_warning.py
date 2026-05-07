#!/usr/bin/env python3
"""
Crash Warning Module — 5-Layer Market Crash Prediction System

Layer 1: Market Euphoria    (Fear&Greed > 75 + VIX < 15)
Layer 2: Yield Curve Anomaly (Inversion → Steepening transition)
Layer 3: Credit Risk Heating (HY spread widening + MOVE rising)
Layer 4: Systemic Risk       (Sector correlation > 0.5 + SKEW > 150)
Layer 5: Technical Extremes  (RSI > 85 + Volume-Price Divergence + Hindenburg Omen)

Data sources: yfinance, FRED API, CNN Fear&Greed API (all free, no auth needed)
"""

import json
import os
import sqlite3
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings('ignore')

# ── Cache ──────────────────────────────────────────────────────────────
CACHE_DB = os.path.join(os.path.dirname(__file__), 'crash_warning_cache.db')

# ── Sector ETFs for correlation analysis ────────────────────────────────
SECTOR_ETFS = ['XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLP', 'XLU', 'XLRE', 'XLB']

# ── Panic/Greed keywords for social signal ─────────────────────────────
PANIC_KEYWORDS = [
    'crash', 'collapse', 'bear market', 'recession', 'sell everything',
    'capitulation', 'panic', 'blood', 'circuit breaker', 'margin call',
    'black swan', 'systemic risk', 'liquidation', 'forced selling',
]
GREED_KEYWORDS = [
    'moon', 'diamond hands', 'to the moon', 'squeeze', 'yolo',
    'tendies', 'rocket', 'lambo', 'guaranteed', 'generational buy',
    'once in a lifetime', 'can\'t lose', 'free money',
]


class CrashWarningSystem:
    """5-Layer Market Crash Prediction System."""

    def __init__(self, tickers: List[str] = None):
        self.tickers = tickers or []
        self._cache_conn = None
        self.layers = {}
        self.composite_score = 0
        self.warning_level = 'NORMAL'
        self.details = {}

    # ── Cache helpers ───────────────────────────────────────────────────

    @property
    def cache(self):
        if self._cache_conn is None:
            self._cache_conn = sqlite3.connect(CACHE_DB)
            self._cache_conn.execute('''
                CREATE TABLE IF NOT EXISTS api_cache (
                    key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            ''')
        return self._cache_conn

    def _get_cached(self, key: str, ttl: int = 3600) -> Optional[str]:
        """Get cached API response. TTL in seconds (default 1 hour)."""
        row = self.cache.execute(
            'SELECT data FROM api_cache WHERE key = ? AND timestamp > ?',
            (key, time.time() - ttl)
        ).fetchone()
        return row[0] if row else None

    def _set_cached(self, key: str, data: str):
        self.cache.execute(
            'INSERT OR REPLACE INTO api_cache (key, data, timestamp) VALUES (?, ?, ?)',
            (key, data, time.time())
        )
        self.cache.commit()

    # ── Data fetchers ───────────────────────────────────────────────────

    def _fetch_yf(self, symbol: str, period: str = '1y') -> Optional[pd.DataFrame]:
        """Fetch yfinance data with caching. Returns DataFrame with standard columns (Close, High, Low, Open, Volume)."""
        cache_key = f'yf:{symbol}:{period}'
        cached = self._get_cached(cache_key, ttl=1800)  # 30-min cache
        if cached:
            df = pd.read_json(cached)
            if not df.empty:
                if not isinstance(df.index, pd.DatetimeIndex):
                    if 'Date' in df.columns:
                        df['Date'] = pd.to_datetime(df['Date'])
                        df = df.set_index('Date')
            return df if not df.empty else None

        try:
            df = yf.download(symbol, period=period, progress=False)
            if df.empty:
                return None
            # Flatten MultiIndex columns from new yfinance
            if isinstance(df.columns, pd.MultiIndex):
                # For single ticker: columns are (Close, TICKER), (High, TICKER), etc.
                # Use first level only, but need to handle duplicates
                # Better: just drop the ticker level
                df.columns = [col[0] for col in df.columns]
            self._set_cached(cache_key, df.to_json())
            return df
        except Exception:
            return None

    def _fetch_fred(self, series_id: str) -> Optional[pd.Series]:
        """Fetch FRED time series data."""
        cache_key = f'fred:{series_id}'
        cached = self._get_cached(cache_key, ttl=86400)  # 24-hour cache (daily data)
        if cached:
            rows = json.loads(cached)
            dates = [r[0] for r in rows]
            vals = [r[1] for r in rows]
            s = pd.Series(vals, index=pd.to_datetime(dates))
            s = s.replace('', np.nan).astype(float)
            return s.dropna()

        try:
            url = f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}'
            r = requests.get(url, timeout=15)
            if r.status_code != 200:
                return None
            lines = r.text.strip().split('\n')
            rows = []
            for line in lines[1:]:  # Skip header
                parts = line.split(',')
                if len(parts) == 2 and parts[1] not in ('.', ''):
                    rows.append((parts[0], float(parts[1])))
            if not rows:
                return None
            self._set_cached(cache_key, json.dumps(rows))
            dates = [r[0] for r in rows]
            vals = [r[1] for r in rows]
            s = pd.Series(vals, index=pd.to_datetime(dates))
            return s.dropna()
        except Exception:
            return None

    def _fetch_fear_greed(self) -> Optional[Dict]:
        """Fetch CNN Fear & Greed Index with sub-components."""
        cache_key = 'cnn:fear_greed'
        cached = self._get_cached(cache_key, ttl=3600)
        if cached:
            return json.loads(cached)

        try:
            url = 'https://production.dataviz.cnn.io/index/fearandgreed/graphdata'
            r = requests.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            }, timeout=15)
            if r.status_code != 200:
                return None
            data = r.json()
            fg = data.get('fear_and_greed', {})

            result = {
                'score': float(fg.get('score', 50)),
                'rating': fg.get('rating', 'neutral'),
                'timestamp': fg.get('timestamp', ''),
                'components': {},
            }

            # Sub-components
            component_map = {
                'market_momentum_sp500': 'Market Momentum S&P500',
                'stock_price_strength': 'Stock Price Strength',
                'stock_price_breadth': 'Stock Price Breadth',
                'put_call_options': 'Put/Call Options',
                'market_volatility_vix': 'Market Volatility VIX',
                'junk_bond_demand': 'Junk Bond Demand',
                'safe_haven_demand': 'Safe Haven Demand',
            }
            for key, label in component_map.items():
                comp = fg.get(key, {})
                if isinstance(comp, dict) and 'score' in comp:
                    result['components'][label] = {
                        'score': float(comp['score']),
                        'rating': comp.get('rating', ''),
                    }

            self._set_cached(cache_key, json.dumps(result))
            return result
        except Exception:
            return None

    # ── Layer 1: Market Euphoria ────────────────────────────────────────

    def _evaluate_euphoria(self) -> Dict:
        """
        Layer 1: Detect market euphoria / complacency.
        Signals: Fear&Greed > 75 (greed), VIX < 15 (complacency),
                 extreme greed in sub-components.
        """
        layer = {
            'name': 'Market Euphoria',
            'score': 0,  # 0-100, higher = more euphoric/dangerous
            'signals': [],
            'details': {},
        }

        # Fear & Greed Index
        fg = self._fetch_fear_greed()
        if fg:
            fg_score = fg['score']
            layer['details']['fear_greed_score'] = fg_score
            layer['details']['fear_greed_rating'] = fg['rating']

            if fg_score >= 80:
                layer['score'] += 35
                layer['signals'].append(f'Fear&Greed={fg_score:.0f} (EXTREME GREED)')
            elif fg_score >= 70:
                layer['score'] += 25
                layer['signals'].append(f'Fear&Greed={fg_score:.0f} (Greed)')
            elif fg_score >= 60:
                layer['score'] += 10
                layer['signals'].append(f'Fear&Greed={fg_score:.0f} (Mild Greed)')
            elif fg_score <= 20:
                layer['score'] -= 10  # Extreme fear = contrarian bullish
                layer['signals'].append(f'Fear&Greed={fg_score:.0f} (EXTREME FEAR - contrarian buy)')

            # Check extreme sub-components
            for comp_name, comp_data in fg.get('components', {}).items():
                cs = comp_data['score']
                cr = comp_data['rating']
                if cs >= 90:
                    layer['score'] += 10
                    layer['signals'].append(f'{comp_name}={cs:.0f} (EXTREME)')
                    layer['details'][f'fg_{comp_name}'] = cs
                elif cs <= 10:
                    layer['score'] += 5  # Extreme fear in component also risky
                    layer['signals'].append(f'{comp_name}={cs:.0f} (EXTREME FEAR)')

            # Safe haven demand extreme = unusual
            shd = fg.get('components', {}).get('Safe Haven Demand', {})
            if shd.get('score', 50) >= 90:
                layer['score'] += 15
                layer['signals'].append('Safe Haven Demand=EXTREME GREED (investors abandoning safety)')
        else:
            layer['details']['fear_greed_score'] = None
            layer['signals'].append('Fear&Greed data unavailable')

        # VIX low = complacency
        vix_df = self._fetch_yf('^VIX', '6mo')
        if vix_df is not None and not vix_df.empty:
            vix_current = float(vix_df['Close'].iloc[-1])
            vix_avg_6m = float(vix_df['Close'].mean())
            layer['details']['vix_current'] = vix_current
            layer['details']['vix_avg_6m'] = vix_avg_6m

            if vix_current < 13:
                layer['score'] += 25
                layer['signals'].append(f'VIX={vix_current:.1f} (EXTREME COMPLACENCY <13)')
            elif vix_current < 15:
                layer['score'] += 15
                layer['signals'].append(f'VIX={vix_current:.1f} (Low complacency <15)')
            elif vix_current > 35:
                layer['score'] -= 5  # High VIX = fear, not euphoria
                layer['signals'].append(f'VIX={vix_current:.1f} (ELEVATED >35 - fear zone)')
            elif vix_current > 25:
                layer['signals'].append(f'VIX={vix_current:.1f} (moderately elevated)')

            # VIX term structure
            vix3m_df = self._fetch_yf('^VIX3M', '5d')
            if vix3m_df is not None and not vix3m_df.empty:
                vix3m = float(vix3m_df['Close'].iloc[-1])
                contango = vix3m - vix_current
                layer['details']['vix3m'] = vix3m
                layer['details']['vix_contango'] = contango
                if contango < -1:  # Backwardation
                    layer['score'] += 20
                    layer['signals'].append(f'VIX BACKWARDATION: VIX3M-VIX={contango:+.1f} (panic signal)')
                elif contango < 0:
                    layer['score'] += 10
                    layer['signals'].append(f'VIX slight backwardation: {contango:+.1f}')

            # VVIX (volatility of volatility)
            vvix_df = self._fetch_yf('^VVIX', '5d')
            if vvix_df is not None and not vvix_df.empty:
                vvix = float(vvix_df['Close'].iloc[-1])
                layer['details']['vvix'] = vvix
                if vvix > 120:
                    layer['score'] += 10
                    layer['signals'].append(f'VVIX={vvix:.0f} (elevated vol-of-vol >120)')

        layer['score'] = max(0, min(100, layer['score']))
        return layer

    # ── Layer 2: Yield Curve Anomaly ────────────────────────────────────

    def _evaluate_yield_curve(self) -> Dict:
        """
        Layer 2: Detect yield curve anomalies.
        Key signal: Inversion → Steepening transition (most reliable crash predictor).
        Lead time: 6-24 months after initial inversion.
        """
        layer = {
            'name': 'Yield Curve Anomaly',
            'score': 0,
            'signals': [],
            'details': {},
        }

        # Method 1: yfinance (real-time)
        tnx = self._fetch_yf('^TNX', '1y')  # 10Y
        irx = self._fetch_yf('^IRX', '1y')  # 13W (3M)

        if tnx is not None and irx is not None and not tnx.empty and not irx.empty:
            common = tnx.index.intersection(irx.index)
            if len(common) > 20:
                spread = pd.Series(
                    tnx.loc[common, 'Close'].values.flatten() - irx.loc[common, 'Close'].values.flatten(),
                    index=common
                )
                current_spread = float(spread.iloc[-1])
                layer['details']['spread_10y_3m'] = current_spread

                # Count inversion days
                inverted_days = int((spread < 0).sum())
                total_days = len(spread)
                layer['details']['inverted_days_1y'] = inverted_days

                if current_spread < -0.5:
                    layer['score'] += 35
                    layer['signals'].append(f'10Y-3M DEEP INVERSION: {current_spread:.2f}% (<-0.5%)')
                elif current_spread < 0:
                    layer['score'] += 25
                    layer['signals'].append(f'10Y-3M INVERTED: {current_spread:.2f}%')
                elif current_spread < 0.3:
                    layer['score'] += 10
                    layer['signals'].append(f'10Y-3M near-flat: {current_spread:.2f}%')

                # Inversion ratio
                inv_ratio = inverted_days / total_days
                layer['details']['inversion_ratio'] = inv_ratio
                if inv_ratio > 0.5:
                    layer['score'] += 15
                    layer['signals'].append(f'Sustained inversion: {inverted_days}/{total_days} days ({inv_ratio:.0%})')

                # Steepening detection (post-inversion = DANGER)
                if len(spread) >= 60:
                    recent_30 = float(spread.iloc[-30:].mean())
                    prev_30 = float(spread.iloc[-60:-30].mean())
                    steepening = recent_30 - prev_30
                    layer['details']['steepening_rate'] = steepening

                    # If was inverted (within last 6 months) and now steepening
                    recent_was_inverted = bool((spread.iloc[-120:] < 0).any()) if len(spread) >= 120 else bool((spread < 0).any())
                    if recent_was_inverted and steepening > 0.2:
                        layer['score'] += 30
                        layer['signals'].append(
                            f'POST-INVERSION STEEPENING: {steepening:+.2f}% change (HIGHEST DANGER - recession imminent)'
                        )
                    elif steepening > 0.3:
                        layer['score'] += 10
                        layer['signals'].append(f'Yield curve steepening: {steepening:+.2f}%')

        # Method 2: FRED (more reliable historical data)
        fred_spread = self._fetch_fred('T10Y2Y')  # 10Y-2Y
        if fred_spread is not None and not fred_spread.empty:
            current_fred = float(fred_spread.iloc[-1])
            layer['details']['fred_10y_2y'] = current_fred

            # Count recent inversion
            recent_90 = fred_spread.last('90D') if len(fred_spread) > 20 else fred_spread
            inv_90 = int((recent_90 < 0).sum())
            layer['details']['inverted_days_90d_fred'] = inv_90

            if current_fred < -0.5:
                layer['score'] += 20
                layer['signals'].append(f'FRED 10Y-2Y deep inversion: {current_fred:.2f}%')
            elif current_fred < 0:
                layer['score'] += 15
                layer['signals'].append(f'FRED 10Y-2Y inverted: {current_fred:.2f}%')

            # Find last inversion period
            inv_periods = fred_spread[fred_spread < 0]
            if not inv_periods.empty:
                last_inv_date = str(inv_periods.index[-1].date())
                layer['details']['last_inversion_date'] = last_inv_date
                days_since_inv = (fred_spread.index[-1] - inv_periods.index[-1]).days
                layer['details']['days_since_last_inversion'] = days_since_inv
                if 30 < days_since_inv < 730:  # 1-24 months post-inversion = danger window
                    layer['score'] += 15
                    layer['signals'].append(
                        f'Last inversion: {last_inv_date} ({days_since_inv}d ago, in danger window 1-24mo)'
                    )
        else:
            layer['signals'].append('FRED yield curve data unavailable')

        layer['score'] = max(0, min(100, layer['score']))
        return layer

    # ── Layer 3: Credit Risk Heating ────────────────────────────────────

    def _evaluate_credit_risk(self) -> Dict:
        """
        Layer 3: Detect credit market stress.
        Signals: HY bond spread widening, MOVE index rising.
        Credit stress precedes equity crashes by weeks.
        """
        layer = {
            'name': 'Credit Risk',
            'score': 0,
            'signals': [],
            'details': {},
        }

        # High Yield Bond Spread (BAML via FRED)
        hy_spread = self._fetch_fred('BAMLH0A0HYM2')
        if hy_spread is not None and not hy_spread.empty:
            current_hy = float(hy_spread.iloc[-1])
            avg_6m = float(hy_spread.last('180D').mean()) if len(hy_spread) > 20 else current_hy
            avg_1y = float(hy_spread.last('365D').mean()) if len(hy_spread) > 40 else avg_6m
            layer['details']['hy_spread_current'] = current_hy
            layer['details']['hy_spread_avg_6m'] = avg_6m
            layer['details']['hy_spread_avg_1y'] = avg_1y

            # Absolute level thresholds
            if current_hy > 7:
                layer['score'] += 35
                layer['signals'].append(f'HY Spread={current_hy:.2f}% (CRISIS LEVEL >7%)')
            elif current_hy > 5:
                layer['score'] += 25
                layer['signals'].append(f'HY Spread={current_hy:.2f}% (ELEVATED >5%)')
            elif current_hy > 4:
                layer['score'] += 10
                layer['signals'].append(f'HY Spread={current_hy:.2f}% (moderately elevated)')

            # Rate of change (widening = stress)
            if len(hy_spread) >= 30:
                change_30d = current_hy - float(hy_spread.iloc[-30])
                layer['details']['hy_spread_change_30d'] = change_30d
                if change_30d > 2:
                    layer['score'] += 25
                    layer['signals'].append(f'HY Spread 30d change: +{change_30d:.2f}% (RAPID WIDENING)')
                elif change_30d > 1:
                    layer['score'] += 15
                    layer['signals'].append(f'HY Spread 30d change: +{change_30d:.2f}% (widening)')
                elif change_30d > 0.5:
                    layer['score'] += 5
                    layer['signals'].append(f'HY Spread 30d change: +{change_30d:.2f}% (slight widening)')

            # Z-score of current vs 1Y
            if len(hy_spread) > 60:
                std_1y = float(hy_spread.last('365D').std()) if len(hy_spread) > 40 else 1.0
                z_score = (current_hy - avg_1y) / max(std_1y, 0.01)
                layer['details']['hy_spread_zscore'] = z_score
                if z_score > 2:
                    layer['score'] += 15
                    layer['signals'].append(f'HY Spread Z-score={z_score:.1f} (>2σ abnormal)')
        else:
            layer['signals'].append('HY Bond spread data unavailable')

        # MOVE Index (Bond volatility)
        move_df = self._fetch_yf('^MOVE', '6mo')
        if move_df is not None and not move_df.empty:
            move_current = float(move_df['Close'].iloc[-1])
            move_avg = float(move_df['Close'].mean())
            layer['details']['move_current'] = move_current
            layer['details']['move_avg_6m'] = move_avg

            if move_current > 130:
                layer['score'] += 25
                layer['signals'].append(f'MOVE={move_current:.0f} (EXTREME bond vol >130)')
            elif move_current > 100:
                layer['score'] += 15
                layer['signals'].append(f'MOVE={move_current:.0f} (elevated bond vol >100)')

            # Rising trend
            if len(move_df) >= 60:
                move_20d = float(move_df['Close'].rolling(20).mean().iloc[-1])
                move_60d = float(move_df['Close'].rolling(60).mean().iloc[-1])
                if move_20d > move_60d * 1.3:
                    layer['score'] += 10
                    layer['signals'].append(f'MOVE 20d/60d ratio: {move_20d/move_60d:.2f} (rising trend)')
        else:
            layer['signals'].append('MOVE index data unavailable')

        layer['score'] = max(0, min(100, layer['score']))
        return layer

    # ── Layer 4: Systemic Risk ──────────────────────────────────────────

    def _evaluate_systemic_risk(self) -> Dict:
        """
        Layer 4: Detect rising systemic risk.
        Signals: Cross-sector correlation > 0.5, SKEW > 150.
        When sectors move together = market driven by macro, not stock-picking.
        """
        layer = {
            'name': 'Systemic Risk',
            'score': 0,
            'signals': [],
            'details': {},
        }

        # Cross-sector correlation
        try:
            prices = yf.download(SECTOR_ETFS, period='6mo', progress=False)['Close']
            if not prices.empty and len(prices.columns) >= 5:
                returns = prices.pct_change().dropna()
                if len(returns) >= 30:
                    # Current 30d correlation
                    recent = returns.iloc[-30:]
                    corr = recent.corr()
                    n = len(corr)
                    mask = ~np.eye(n, dtype=bool)
                    avg_corr = float(corr.values[mask].mean())
                    layer['details']['sector_correlation_30d'] = avg_corr

                    # Rolling correlation history
                    rolling_corrs = []
                    for i in range(30, len(returns)):
                        window = returns.iloc[i-30:i]
                        rc = window.corr()
                        rolling_corrs.append(float(rc.values[mask].mean()))

                    if rolling_corrs:
                        current_rc = rolling_corrs[-1]
                        mean_rc = float(np.mean(rolling_corrs))
                        std_rc = float(np.std(rolling_corrs))
                        layer['details']['correlation_current'] = current_rc
                        layer['details']['correlation_mean'] = mean_rc
                        layer['details']['correlation_std'] = std_rc

                        if current_rc > 0.65:
                            layer['score'] += 35
                            layer['signals'].append(f'Sector correlation={current_rc:.3f} (DANGER ZONE >0.65)')
                        elif current_rc > 0.5:
                            layer['score'] += 25
                            layer['signals'].append(f'Sector correlation={current_rc:.3f} (ELEVATED >0.5)')
                        elif current_rc > 0.4:
                            layer['score'] += 10
                            layer['signals'].append(f'Sector correlation={current_rc:.3f} (moderately elevated)')

                        # Correlation spike (>2σ)
                        if current_rc > mean_rc + 2 * std_rc:
                            layer['score'] += 15
                            layer['signals'].append(
                                f'Correlation SPIKE: {current_rc:.3f} (>2σ from mean {mean_rc:.3f})'
                            )

                        # Rapid increase (>0.1 in 2 weeks)
                        if len(rolling_corrs) >= 10:
                            prev_2w = np.mean(rolling_corrs[-14:-7]) if len(rolling_corrs) >= 14 else rolling_corrs[-7]
                            corr_change = current_rc - prev_2w
                            layer['details']['correlation_2w_change'] = float(corr_change)
                            if corr_change > 0.1:
                                layer['score'] += 15
                                layer['signals'].append(f'Correlation rapid rise: +{corr_change:.3f} in 2 weeks')
        except Exception as e:
            layer['signals'].append(f'Sector correlation calculation error: {e}')

        # SKEW Index (tail risk)
        skew_df = self._fetch_yf('^SKEW', '6mo')
        if skew_df is not None and not skew_df.empty:
            skew_current = float(skew_df['Close'].iloc[-1])
            skew_avg = float(skew_df['Close'].mean())
            layer['details']['skew_current'] = skew_current
            layer['details']['skew_avg_6m'] = skew_avg

            if skew_current > 160:
                layer['score'] += 25
                layer['signals'].append(f'SKEW={skew_current:.0f} (EXTREME tail risk >160)')
            elif skew_current > 150:
                layer['score'] += 20
                layer['signals'].append(f'SKEW={skew_current:.0f} (ELEVATED tail risk >150)')
            elif skew_current > 140:
                layer['score'] += 10
                layer['signals'].append(f'SKEW={skew_current:.0f} (moderately elevated)')

            # Rising SKEW
            if len(skew_df) >= 60:
                skew_change = skew_current - float(skew_df['Close'].rolling(60).mean().iloc[-1])
                if skew_change > 15:
                    layer['score'] += 10
                    layer['signals'].append(f'SKEW rising by +{skew_change:.0f} in 60d')
        else:
            layer['signals'].append('SKEW index data unavailable')

        layer['score'] = max(0, min(100, layer['score']))
        return layer

    # ── Layer 5: Technical Extremes ─────────────────────────────────────

    def _evaluate_technical_extremes(self) -> Dict:
        """
        Layer 5: Detect technical extreme conditions.
        Signals: RSI extreme, Volume-Price divergence, Hindenburg Omen.
        """
        layer = {
            'name': 'Technical Extremes',
            'score': 0,
            'signals': [],
            'details': {},
        }

        # SPY technical analysis
        spy = self._fetch_yf('SPY', '6mo')
        if spy is not None and not spy.empty:
            close = spy['Close'].values.flatten().astype(float)
            volume = spy['Volume'].values.flatten().astype(float)

            # RSI-14
            deltas = np.diff(close)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = pd.Series(gains).rolling(14).mean().values
            avg_loss = pd.Series(losses).rolling(14).mean().values
            rs = np.where(avg_loss > 0, avg_gain / avg_loss, 100)
            rsi = 100 - (100 / (1 + rs))
            current_rsi = float(rsi[-1]) if not np.isnan(rsi[-1]) else 50
            layer['details']['spy_rsi_14'] = current_rsi

            if current_rsi > 85:
                layer['score'] += 30
                layer['signals'].append(f'SPY RSI-14={current_rsi:.1f} (EXTREME OVERBOUGHT >85)')
            elif current_rsi > 75:
                layer['score'] += 15
                layer['signals'].append(f'SPY RSI-14={current_rsi:.1f} (overbought >75)')
            elif current_rsi < 25:
                layer['score'] += 5  # Oversold = potential bounce, not crash signal
                layer['signals'].append(f'SPY RSI-14={current_rsi:.1f} (oversold <25)')

            # Volume-Price divergence (price up + volume declining)
            if len(close) >= 20:
                vol_ma_20 = np.mean(volume[-20:])
                vol_ma_50 = np.mean(volume[-50:]) if len(volume) >= 50 else vol_ma_20
                price_up = close[-1] > close[-20]
                vol_declining = vol_ma_20 < vol_ma_50 * 0.85

                layer['details']['vol_ratio_20_50'] = vol_ma_20 / max(vol_ma_50, 1)

                if price_up and vol_declining:
                    layer['score'] += 20
                    layer['signals'].append(
                        f'BEARISH DIVERGENCE: Price up + Volume declining (20/50 ratio={vol_ma_20/vol_ma_50:.2f})'
                    )
                elif price_up and vol_ma_20 < vol_ma_50:
                    layer['score'] += 10
                    layer['signals'].append(f'Mild volume decline while price rising')

                # Volume spike (capitulation or panic)
                vol_today = volume[-1]
                vol_avg_20 = np.mean(volume[-20:])
                if vol_today > vol_avg_20 * 3:
                    layer['score'] += 15
                    layer['signals'].append(f'VOLUME SPIKE: {vol_today/vol_avg_20:.1f}x average (possible capitulation)')

            # Distance from 200d MA (major trend indicator)
            if len(close) >= 200:
                ma_200 = np.mean(close[-200:])
                pct_from_200 = (close[-1] / ma_200 - 1) * 100
                layer['details']['pct_from_200ma'] = pct_from_200
                if pct_from_200 > 20:
                    layer['score'] += 20
                    layer['signals'].append(f'SPY {pct_from_200:+.1f}% above 200d MA (EXTREME deviation >20%)')
                elif pct_from_200 > 12:
                    layer['score'] += 10
                    layer['signals'].append(f'SPY {pct_from_200:+.1f}% above 200d MA (elevated)')

        # Hindenburg Omen (simplified with available tickers)
        near_high = 0
        near_low = 0
        total = 0
        for t in self.tickers[:50]:  # Sample up to 50 tickers
            try:
                df = yf.download(t, period='1y', progress=False)
                if df is not None and not df.empty and len(df) > 50:
                    total += 1
                    # Handle MultiIndex columns from yfinance
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = [col[0] for col in df.columns]
                    high_252 = float(df['High'].max())
                    low_252 = float(df['Low'].min())
                    latest = float(df['Close'].iloc[-1])
                    if latest >= high_252 * 0.98:
                        near_high += 1
                    if latest <= low_252 * 1.02:
                        near_low += 1
            except Exception:
                continue

        if total > 10:
            pct_high = near_high / total * 100
            pct_low = near_low / total * 100
            layer['details']['hindenburg_pct_high'] = pct_high
            layer['details']['hindenburg_pct_low'] = pct_low
            layer['details']['hindenburg_total_sampled'] = total

            if pct_high > 2.2 and pct_low > 2.2:
                layer['score'] += 30
                layer['signals'].append(
                    f'HINDENBURG OMEN: {pct_high:.1f}% near high + {pct_low:.1f}% near low (both >2.2%)'
                )
            elif pct_low > 5:
                layer['score'] += 15
                layer['signals'].append(f'Elevated 52w lows: {pct_low:.1f}% of tickers near low')
            elif pct_high > 50:
                layer['score'] += 5
                layer['signals'].append(f'Broad strength: {pct_high:.1f}% near 52w high (possible euphoria)')

        layer['score'] = max(0, min(100, layer['score']))
        return layer

    # ── Social Panic Bonus ──────────────────────────────────────────────

    def _evaluate_social_panic(self) -> Dict:
        """Bonus: Detect social media panic/euphoria from Reddit posts stored in SQLite."""
        layer = {
            'name': 'Social Panic',
            'score': 0,
            'signals': [],
            'details': {},
        }

        try:
            from social_sentiment import SocialSentimentEngine
            engine = SocialSentimentEngine()
            engine.fetch_wsb_data(limit_per_subreddit=10)

            # Read posts from SQLite DB
            db_path = engine.data_store.db_path
            conn = sqlite3.connect(db_path)
            cutoff = int(time.time()) - 86400 * 7  # 7 days ago
            rows = conn.execute(
                "SELECT title, body FROM reddit_posts WHERE fetched_at > ? ORDER BY fetched_at DESC LIMIT 500",
                (cutoff,)
            ).fetchall()
            conn.close()

            all_text = ''
            for title, body in rows:
                all_text += (title + ' ' + (body or '') + ' ').lower()

            if all_text:
                panic_count = sum(all_text.count(w) for w in PANIC_KEYWORDS)
                greed_count = sum(all_text.count(w) for w in GREED_KEYWORDS)
                total_kw = panic_count + greed_count
                panic_ratio = panic_count / max(1, total_kw)
                layer['details']['panic_keywords'] = panic_count
                layer['details']['greed_keywords'] = greed_count
                layer['details']['panic_ratio'] = panic_ratio
                layer['details']['posts_analyzed'] = len(rows)

                if panic_ratio > 0.8:
                    layer['score'] += 25
                    layer['signals'].append(f'Social PANIC: {panic_count} panic vs {greed_count} greed keywords')
                elif panic_ratio > 0.6:
                    layer['score'] += 15
                    layer['signals'].append(f'Social fear dominant: {panic_count} vs {greed_count}')
                elif panic_ratio < 0.15:
                    layer['score'] += 20
                    layer['signals'].append(f'Social EUPHORIA: {greed_count} greed vs {panic_count} panic keywords')
                elif panic_ratio < 0.3:
                    layer['score'] += 10
                    layer['signals'].append(f'Social greed dominant: {greed_count} vs {panic_count}')
            else:
                layer['signals'].append('No social text data available')
        except Exception as e:
            layer['signals'].append(f'Social panic analysis skipped: {e}')

        layer['score'] = max(0, min(100, layer['score']))
        return layer

    # ── Composite Score & Warning Level ─────────────────────────────────

    def _compute_composite(self) -> Tuple[int, str]:
        """
        Compute composite crash warning score (0-100).
        
        Weighting:
          Layer 1 (Euphoria):      20%
          Layer 2 (Yield Curve):   30%  (most reliable historically)
          Layer 3 (Credit Risk):   20%
          Layer 4 (Systemic Risk): 15%
          Layer 5 (Technical):     15%
        """
        weights = {
            'Market Euphoria': 0.20,
            'Yield Curve Anomaly': 0.30,
            'Credit Risk': 0.20,
            'Systemic Risk': 0.15,
            'Technical Extremes': 0.15,
        }

        composite = 0
        for name, weight in weights.items():
            layer = self.layers.get(name, {})
            score = layer.get('score', 0)
            composite += score * weight

        composite = int(round(composite))

        # Warning level
        if composite >= 70:
            level = '🔴 CRASH WARNING'
        elif composite >= 50:
            level = '🟠 ELEVATED RISK'
        elif composite >= 30:
            level = '🟡 CAUTION'
        elif composite >= 15:
            level = '🟢 WATCH'
        else:
            level = '✅ NORMAL'

        # Multi-layer confirmation bonus
        active_layers = sum(1 for l in self.layers.values() if l.get('score', 0) >= 25)
        if active_layers >= 4:
            composite = min(100, composite + 15)
            level = '🔴 CRASH WARNING' if composite >= 70 else '🟠 ELEVATED RISK'
        elif active_layers >= 3:
            composite = min(100, composite + 8)

        return composite, level

    # ── Main entry point ────────────────────────────────────────────────

    def run_analysis(self) -> Dict:
        """Run full 5-layer crash warning analysis."""
        print('[CrashWarning] Running 5-layer market crash analysis...')

        # Layer 1: Market Euphoria
        print('  Layer 1: Market Euphoria...')
        self.layers['Market Euphoria'] = self._evaluate_euphoria()

        # Layer 2: Yield Curve Anomaly
        print('  Layer 2: Yield Curve Anomaly...')
        self.layers['Yield Curve Anomaly'] = self._evaluate_yield_curve()

        # Layer 3: Credit Risk
        print('  Layer 3: Credit Risk...')
        self.layers['Credit Risk'] = self._evaluate_credit_risk()

        # Layer 4: Systemic Risk
        print('  Layer 4: Systemic Risk...')
        self.layers['Systemic Risk'] = self._evaluate_systemic_risk()

        # Layer 5: Technical Extremes
        print('  Layer 5: Technical Extremes...')
        self.layers['Technical Extremes'] = self._evaluate_technical_extremes()

        # Bonus: Social Panic
        print('  Bonus: Social Panic...')
        self.layers['Social Panic'] = self._evaluate_social_panic()

        # Composite
        self.composite_score, self.warning_level = self._compute_composite()

        # Summary
        all_signals = []
        for layer in self.layers.values():
            all_signals.extend(layer.get('signals', []))

        result = {
            'composite_score': self.composite_score,
            'warning_level': self.warning_level,
            'active_layers': sum(1 for l in self.layers.values() if l.get('score', 0) >= 25),
            'layers': {},
            'all_signals': all_signals,
        }

        for name, layer in self.layers.items():
            result['layers'][name] = {
                'score': layer['score'],
                'signals': layer['signals'],
                'details': layer.get('details', {}),
            }

        # Print summary
        print(f'\n[CrashWarning] ── RESULT ──')
        print(f'  Composite Score: {self.composite_score}/100')
        print(f'  Warning Level: {self.warning_level}')
        print(f'  Active Layers: {result["active_layers"]}/5')
        for name, layer in self.layers.items():
            sig_count = len(layer.get('signals', []))
            print(f'  {name}: {layer["score"]}/100 ({sig_count} signals)')
        if all_signals:
            print(f'\n  Key Signals:')
            for sig in all_signals[:10]:
                print(f'    ⚠️  {sig}')

        return result


# ── CLI test ────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # Default V4 tickers for Hindenburg check
    DEFAULT_TICKERS = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD',
        'INTC', 'QCOM', 'AVGO', 'TXN', 'MU', 'CRM', 'ORCL', 'PYPL',
        'COIN', 'GME', 'AMC', 'BABA', 'NIO', 'PLTR', 'SOFI', 'RIVN',
        'SNAP', 'SHOP', 'SQ', 'UBER', 'LYFT', 'ABNB', 'COIN', 'HOOD',
    ]
    system = CrashWarningSystem(tickers=DEFAULT_TICKERS)
    result = system.run_analysis()

    # Save JSON
    output_file = os.path.join(os.path.dirname(__file__), 'crash_warning_result.json')
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f'\nResult saved to {output_file}')
