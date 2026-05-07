#!/usr/bin/env python3
"""
TradingView Screener Module for Alpha Stock Finder V4

Wraps the tradingview-screener package to fetch enhanced market data:
- TV community consensus (Recommend.All / MA / Other)
- Fundamentals (gross_margin, operating_margin, return_on_equity, debt_to_equity)
- Advanced technical indicators (RSI, MACD, HullMA9, Ichimoku, MoneyFlow, Bollinger Bands)

Data is fetched in batch queries of up to 25 tickers per request (TV API limit).
Results are cached with a 15-minute TTL to avoid redundant API calls within a single scan.
If the TV API fails entirely, an empty dict is returned so the scanner can still
operate using V3 yfinance data as a fallback.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
from tradingview_screener import Query

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

# TV fields that reliably return data (verified with tradingview-screener v3.1.0)
TV_FIELDS = [
    'name',
    'close',
    'volume',
    'Recommend.All',
    'Recommend.MA',
    'Recommend.Other',
    'RSI',
    'MACD.macd',
    'MACD.signal',
    'HullMA9',
    'Ichimoku.CLine',
    'MoneyFlow',
    'BB.upper',
    'BB.lower',
    'gross_margin',
    'operating_margin',
    'return_on_equity',
    'debt_to_equity',
    'float_shares_outstanding',
]

# Maximum tickers per API request (TV limit)
BATCH_SIZE = 25

# Delay between batch requests in seconds (avoid rate-limiting)
BATCH_DELAY_SEC = 1.0

# Retry settings
MAX_RETRIES = 3
RETRY_BACKOFF_SEC = 2.0

# Cache TTL in minutes
CACHE_TTL_MINUTES = 15

# Exchange mapping: tickers that trade on NYSE instead of NASDAQ
# Verified via tradingview-screener API — these tickers only return data with NYSE: prefix
NYSE_TICKERS = {
    # Original NYSE list
    'V', 'MA', 'DIS', 'CRM', 'ON', 'MCHP', 'SWKS',
    'ENPH', 'SEDG', 'ORCL', 'NXPI', 'AVGO', 'TXN',
    'WDC', 'STX', 'BABA',
    # Additional NYSE tickers found via API testing
    'NOW', 'SNOW', 'SPOT', 'AI', 'BBAI', 'IONQ',
    'QBTS', 'GME', 'AMC', 'BB', 'NIO', 'RDDT', 'SSTK',
}

# V4 ticker pool (same as alpha_scanner_v4.py)
V4_TICKERS = [
    # Tech giants
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    # Semiconductors
    'AMD', 'INTC', 'QCOM', 'AVGO', 'TXN', 'NXPI', 'MU', 'AMAT', 'LRCX', 'KLAC',
    'MRVL', 'ON', 'MCHP', 'SWKS', 'ENPH', 'SEDG',
    # Software
    'CRM', 'ORCL', 'ADBE', 'NOW', 'SNOW', 'PLTR', 'MDB',
    # Fintech
    'V', 'MA', 'PYPL', 'SQ', 'COIN', 'HOOD', 'SOFI',
    # Streaming / Media
    'NFLX', 'DIS', 'SPOT',
    # AI theme
    'SMCI', 'ARM', 'AI', 'SOUN', 'BBAI', 'RKLB', 'IONQ', 'RGTI', 'QBTS',
    # Meme / WSB favorites
    'GME', 'AMC', 'BB', 'RIVN', 'LCID', 'NIO',
    # Other hot
    'RDDT', 'DDOG', 'ZS', 'CRWD', 'SSTK', 'WDC', 'STX',
    # Chinese ADR
    'BABA', 'JD', 'PDD', 'BIDU',
    # Crypto adjacent
    'MSTR', 'RIOT', 'CLSK', 'MARA',
]


# ── Helper: Build EXCHANGE:TICKER strings ────────────────────────────────────

def _build_exchange_tickers(tickers: List[str]) -> List[str]:
    """
    Convert plain ticker symbols to EXCHANGE:TICKER format.
    Uses NASDAQ as default; NYSE_TICKERS set overrides for known NYSE stocks.
    """
    result = []
    for t in tickers:
        exchange = 'NYSE' if t in NYSE_TICKERS else 'NASDAQ'
        result.append(f'{exchange}:{t}')
    return result


def _strip_exchange_prefix(exchange_ticker: str) -> str:
    """Strip the exchange prefix from 'EXCHANGE:TICKER' → 'TICKER'."""
    if ':' in exchange_ticker:
        return exchange_ticker.split(':', 1)[1]
    return exchange_ticker


# ── Main Class ────────────────────────────────────────────────────────────────

class TradingViewDataFetcher:
    """
    Fetches enhanced market data from TradingView via the tradingview-screener
    package. Provides consensus signals, fundamental scores, and technical
    enhancement scores for the V4 ticker pool.
    """

    def __init__(self):
        # Simple in-memory cache: {ticker: {data_dict, timestamp}}
        self._cache: Dict[str, dict] = {}
        self._cache_timestamp: Optional[datetime] = None
        # Track tickers that the API could not find (avoid retrying within TTL)
        self._failed_tickers: set = set()

    # ── Cache management ──────────────────────────────────────────────────

    def _is_cache_valid(self) -> bool:
        """Check if the cache exists and is within TTL."""
        if self._cache_timestamp is None or not self._cache:
            return False
        age = datetime.now() - self._cache_timestamp
        return age < timedelta(minutes=CACHE_TTL_MINUTES)

    def _invalidate_cache(self):
        """Clear the cache and failed-ticker tracking."""
        self._cache = {}
        self._cache_timestamp = None
        self._failed_tickers = set()

    # ── Core API fetch ────────────────────────────────────────────────────

    def _fetch_batch(self, exchange_tickers: List[str]) -> Optional[pd.DataFrame]:
        """
        Execute a single batch query against the TradingView screener API.
        Returns a DataFrame on success, or None on failure after all retries.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                q = Query()
                q.set_markets('america')
                q.set_tickers(*exchange_tickers)
                q.select(*TV_FIELDS)
                q.limit(len(exchange_tickers))

                status, df = q.get_scanner_data()

                if not df.empty:
                    logger.debug(
                        'TV batch OK: %d tickers returned (status=%s)',
                        len(df), status
                    )
                    return df
                else:
                    # Empty result may mean tickers not found on specified exchange
                    logger.debug(
                        'TV batch empty (attempt %d/%d, status=%s): %s',
                        attempt, MAX_RETRIES, status, exchange_tickers[:3]
                    )

            except Exception as exc:
                logger.warning(
                    'TV API error (attempt %d/%d): %s',
                    attempt, MAX_RETRIES, exc
                )

            # Backoff before retry (skip on last attempt)
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_SEC * attempt
                logger.debug('Retrying in %.1fs ...', wait)
                time.sleep(wait)

        return None

    def _fetch_with_nasdaq_fallback(self, exchange_tickers: List[str]) -> pd.DataFrame:
        """
        Fetch a batch. If any NYSE tickers return no data, retry them on NASDAQ.
        Some tickers may be listed on NASDAQ even if we expected NYSE.
        Returns the combined DataFrame.
        """
        result_df = pd.DataFrame()
        remaining = list(exchange_tickers)

        for _ in range(2):  # Max 2 passes: original exchange, then NASDAQ fallback
            if not remaining:
                break

            df = self._fetch_batch(remaining)
            if df is not None and not df.empty:
                result_df = pd.concat([result_df, df], ignore_index=True)

                # Identify tickers that were NOT returned (need fallback)
                returned_tickers = set(df['ticker'].tolist())
                remaining = [
                    t for t in remaining
                    if t not in returned_tickers
                ]

                if not remaining:
                    break

                # Try NASDAQ prefix for any NYSE tickers that were not returned
                nasdaq_fallback = []
                for t in remaining:
                    if t.startswith('NYSE:'):
                        ticker_sym = t.split(':', 1)[1]
                        nasdaq_fallback.append(f'NASDAQ:{ticker_sym}')
                    else:
                        # Already NASDAQ, won't help to retry
                        logger.debug('Ticker %s returned no data, skipping', t)
                remaining = nasdaq_fallback
            else:
                break

        return result_df

    # ── Public API ────────────────────────────────────────────────────────

    def fetch_ticker_data(self, tickers: List[str] = None) -> Dict[str, dict]:
        """
        Fetch TradingView data for all given tickers in batched queries.
        Returns a dict mapping plain ticker symbol → tv_data_dict.

        Each tv_data_dict contains:
            close, volume, name,
            recommend_all, recommend_ma, recommend_other,
            rsi, macd, macd_signal, hull_ma9, ichimoku_cline,
            money_flow, bb_upper, bb_lower,
            gross_margin, operating_margin, return_on_equity,
            debt_to_equity, float_shares_outstanding

        If the TV API fails entirely, returns an empty dict so the scanner
        can still operate with V3 yfinance data.
        """
        if tickers is None:
            tickers = V4_TICKERS

        # Serve cached data for already-fetched tickers, determine what's missing
        cached_results = {}
        missing_tickers = []

        if self._is_cache_valid():
            for t in tickers:
                if t in self._cache:
                    cached_results[t] = self._cache[t]
                elif t not in self._failed_tickers:
                    # Only fetch if not previously failed
                    missing_tickers.append(t)
                # else: ticker is in _failed_tickers — skip it
            if not missing_tickers:
                logger.info('TV cache hit (%d tickers, age=%s)',
                            len(cached_results),
                            datetime.now() - self._cache_timestamp)
                return cached_results
            else:
                logger.info('TV cache partial hit: %d cached, %d to fetch',
                            len(cached_results), len(missing_tickers))
                tickers_to_fetch = missing_tickers
        else:
            # Cache expired or empty — fetch everything
            self._cache = {}
            self._cache_timestamp = None
            tickers_to_fetch = list(tickers)

        logger.info('Fetching TV data for %d tickers in batches of %d ...',
                     len(tickers_to_fetch), BATCH_SIZE)

        # Build EXCHANGE:TICKER list (only for tickers we need to fetch)
        exchange_tickers = _build_exchange_tickers(tickers_to_fetch)

        # Split into batches
        all_results: Dict[str, dict] = {}

        for i in range(0, len(exchange_tickers), BATCH_SIZE):
            batch = exchange_tickers[i:i + BATCH_SIZE]
            logger.debug('Batch %d/%d: %s',
                         i // BATCH_SIZE + 1,
                         (len(exchange_tickers) + BATCH_SIZE - 1) // BATCH_SIZE,
                         batch[:3])

            try:
                df = self._fetch_with_nasdaq_fallback(batch)

                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        ticker_sym = _strip_exchange_prefix(str(row.get('ticker', '')))
                        tv_data = {
                            'name': row.get('name'),
                            'close': row.get('close'),
                            'volume': row.get('volume'),
                            'recommend_all': row.get('Recommend.All'),
                            'recommend_ma': row.get('Recommend.MA'),
                            'recommend_other': row.get('Recommend.Other'),
                            'rsi': row.get('RSI'),
                            'macd': row.get('MACD.macd'),
                            'macd_signal': row.get('MACD.signal'),
                            'hull_ma9': row.get('HullMA9'),
                            'ichimoku_cline': row.get('Ichimoku.CLine'),
                            'money_flow': row.get('MoneyFlow'),
                            'bb_upper': row.get('BB.upper'),
                            'bb_lower': row.get('BB.lower'),
                            'gross_margin': row.get('gross_margin'),
                            'operating_margin': row.get('operating_margin'),
                            'return_on_equity': row.get('return_on_equity'),
                            'debt_to_equity': row.get('debt_to_equity'),
                            'float_shares_outstanding': row.get('float_shares_outstanding'),
                        }
                        all_results[ticker_sym] = tv_data

            except Exception as exc:
                logger.error('Unhandled error in batch processing: %s', exc)

            # Rate-limit between batches
            if i + BATCH_SIZE < len(exchange_tickers):
                time.sleep(BATCH_DELAY_SEC)

        # Update cache: merge newly fetched data into existing cache
        self._cache.update(all_results)
        self._cache_timestamp = datetime.now()

        # Record tickers that were requested but returned no data (failed)
        fetched_symbols = set(_strip_exchange_prefix(t) for t in exchange_tickers)
        returned_symbols = set(all_results.keys())
        failed = fetched_symbols - returned_symbols
        self._failed_tickers.update(failed)
        if failed:
            logger.debug('Recorded %d failed tickers: %s', len(failed), failed)

        # Merge cached results with newly fetched results
        merged = {**cached_results, **all_results}

        logger.info('TV fetch complete: %d/%d tickers returned data (cached=%d, new=%d)',
                     len(merged), len(tickers), len(cached_results), len(all_results))

        return merged

    # ── Scoring helpers ───────────────────────────────────────────────────

    @staticmethod
    def get_consensus_signal(recommend_all: float) -> str:
        """
        Convert TradingView Recommend.All value (-1 to +1) to a signal label.

        Thresholds (based on TV community consensus scale):
            >= 0.5  → strong_buy
            >= 0.1  → buy
            > -0.1  → neutral
            > -0.5  → sell
            <= -0.5 → strong_sell
        """
        if recommend_all is None or pd.isna(recommend_all):
            return 'unknown'

        val = float(recommend_all)

        if val >= 0.5:
            return 'strong_buy'
        elif val >= 0.1:
            return 'buy'
        elif val > -0.1:
            return 'neutral'
        elif val > -0.5:
            return 'sell'
        else:
            return 'strong_sell'

    @staticmethod
    def get_fundamentals_score(tv_data: dict) -> float:
        """
        Score fundamentals from 0 to 100 based on margin, ROE, and D/E ratio.

        Components (each scored 0-25, then summed):
            1. Gross margin    — higher is better (0-100% maps to 0-25)
            2. Operating margin — higher is better (0-50% maps to 0-25)
            3. Return on equity — higher is better (0-100% maps to 0-25)
            4. Debt-to-equity   — lower is better (<0.5=25, >=3.0=0)

        Returns a float in [0, 100]. Returns 50.0 (neutral) if no fundamental
        data is available.
        """
        if not tv_data:
            return 50.0

        score = 0.0
        components = 0

        # Gross margin (typically 0-1, i.e. 0%-100%)
        gm = tv_data.get('gross_margin')
        if gm is not None and not pd.isna(gm):
            gm_val = float(gm)
            # Clamp to [0, 1]
            gm_val = max(0.0, min(1.0, gm_val))
            score += (gm_val / 1.0) * 25  # 0-100% → 0-25 points
            components += 1

        # Operating margin (typically 0-0.5, i.e. 0%-50%)
        om = tv_data.get('operating_margin')
        if om is not None and not pd.isna(om):
            om_val = float(om)
            om_val = max(0.0, min(0.5, om_val))
            score += (om_val / 0.5) * 25  # 0-50% → 0-25 points
            components += 1

        # Return on equity (typically 0-1, i.e. 0%-100%)
        roe = tv_data.get('return_on_equity')
        if roe is not None and not pd.isna(roe):
            roe_val = float(roe)
            # ROE can exceed 1.0 for very profitable companies; clamp at 1.0
            roe_val = max(0.0, min(1.0, roe_val))
            score += (roe_val / 1.0) * 25  # 0-100% → 0-25 points
            components += 1

        # Debt-to-equity (lower is better: <0.5 = max, >=3.0 = min)
        de = tv_data.get('debt_to_equity')
        if de is not None and not pd.isna(de):
            de_val = float(de)
            de_val = max(0.0, de_val)
            if de_val <= 0.5:
                de_score = 25.0
            elif de_val >= 3.0:
                de_score = 0.0
            else:
                # Linear decline from 0.5 to 3.0
                de_score = 25.0 * (1.0 - (de_val - 0.5) / (3.0 - 0.5))
            score += de_score
            components += 1

        if components == 0:
            return 50.0  # Neutral when no data available

        # Scale actual components to full 100-point range
        # If we only have 3 of 4 components, scale up proportionally
        max_possible = components * 25
        return round((score / max_possible) * 100, 1) if max_possible > 0 else 50.0

    @staticmethod
    def get_technical_enhancement_score(tv_data: dict) -> float:
        """
        Score enhanced technical indicators from 0 to 100.

        Components (each scored 0-20, then summed):
            1. Recommend.All consensus — strong_buy=20, strong_sell=0
            2. RSI — 50 is neutral (10), extremes (30/70) are signals
            3. MACD vs signal — MACD above signal is bullish
            4. Hull MA9 vs close — price above Hull MA is bullish
            5. Money Flow — above 0 is bullish, below 0 is bearish

        Returns a float in [0, 100]. Returns 50.0 (neutral) if no technical
        data is available.
        """
        if not tv_data:
            return 50.0

        score = 0.0
        components = 0

        # 1. Recommend.All consensus (-1 to 1 → 0 to 20)
        rec = tv_data.get('recommend_all')
        if rec is not None and not pd.isna(rec):
            rec_val = float(rec)
            # Map [-1, 1] → [0, 20]
            score += ((rec_val + 1.0) / 2.0) * 20
            components += 1

        # 2. RSI (0-100 scale; 50 is neutral = 10 pts)
        rsi = tv_data.get('rsi')
        if rsi is not None and not pd.isna(rsi):
            rsi_val = float(rsi)
            rsi_val = max(0.0, min(100.0, rsi_val))
            # Map RSI 0→0, 50→10, 100→20
            score += (rsi_val / 100.0) * 20
            components += 1

        # 3. MACD vs signal line
        macd = tv_data.get('macd')
        macd_sig = tv_data.get('macd_signal')
        if macd is not None and macd_sig is not None \
                and not pd.isna(macd) and not pd.isna(macd_sig):
            macd_val = float(macd)
            sig_val = float(macd_sig)
            diff = macd_val - sig_val
            # Normalize: diff in [-5, +5] → [0, 20]
            diff_clamped = max(-5.0, min(5.0, diff))
            score += ((diff_clamped + 5.0) / 10.0) * 20
            components += 1

        # 4. Hull MA9 vs close price
        hull_ma = tv_data.get('hull_ma9')
        close = tv_data.get('close')
        if hull_ma is not None and close is not None \
                and not pd.isna(hull_ma) and not pd.isna(close) \
                and float(hull_ma) > 0:
            # Price above Hull MA = bullish
            pct_diff = (float(close) - float(hull_ma)) / float(hull_ma)
            pct_diff = max(-0.1, min(0.1, pct_diff))  # Clamp ±10%
            # Map [-10%, +10%] → [0, 20]
            score += ((pct_diff + 0.1) / 0.2) * 20
            components += 1

        # 5. Money Flow (Chaikin-like, range roughly -100 to 100)
        mf = tv_data.get('money_flow')
        if mf is not None and not pd.isna(mf):
            mf_val = float(mf)
            # Map [-100, 100] → [0, 20]
            mf_clamped = max(-100.0, min(100.0, mf_val))
            score += ((mf_clamped + 100.0) / 200.0) * 20
            components += 1

        if components == 0:
            return 50.0

        # Scale to full 100-point range
        max_possible = components * 20
        return round((score / max_possible) * 100, 1) if max_possible > 0 else 50.0


# ── Standalone test ──────────────────────────────────────────────────────────

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
        datefmt='%H:%M:%S',
    )

    fetcher = TradingViewDataFetcher()

    # Fetch data for a small test set first
    test_tickers = ['NVDA', 'AAPL', 'V', 'DIS', 'TSLA', 'BABA', 'AMD']
    print(f'\n=== Test fetch for {len(test_tickers)} tickers ===')
    data = fetcher.fetch_ticker_data(test_tickers)

    for ticker, tv in data.items():
        consensus = fetcher.get_consensus_signal(tv.get('recommend_all'))
        fund_score = fetcher.get_fundamentals_score(tv)
        tech_score = fetcher.get_technical_enhancement_score(tv)
        print(
            f'{ticker:6s} | close={tv.get("close", "N/A"):>10} | '
            f'Rec.All={tv.get("recommend_all", "N/A"):>7} → {consensus:12s} | '
            f'Fund={fund_score:5.1f} | Tech={tech_score:5.1f} | '
            f'RSI={tv.get("rsi", "N/A"):>7} | MACD={tv.get("macd", "N/A"):>8}'
        )

    # Show tickers that had no data
    missing = [t for t in test_tickers if t not in data]
    if missing:
        print(f'\nMissing data for: {missing}')

    # Full V4 pool fetch
    print(f'\n=== Full V4 pool fetch ({len(V4_TICKERS)} tickers) ===')
    full_data = fetcher.fetch_ticker_data(V4_TICKERS)
    print(f'Returned data for {len(full_data)}/{len(V4_TICKERS)} tickers')
    missing_full = [t for t in V4_TICKERS if t not in full_data]
    if missing_full:
        print(f'Missing: {missing_full}')

    # Test cache (re-fetch same pool — should hit cache, instant)
    print('\n=== Cache test (re-fetch same pool, should be instant) ===')
    t0 = time.time()
    cached = fetcher.fetch_ticker_data(V4_TICKERS)
    elapsed = time.time() - t0
    print(f'Cache returned {len(cached)} tickers in {elapsed:.3f}s '
          f'(should be <0.01s)')
