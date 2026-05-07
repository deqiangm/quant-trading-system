#!/usr/bin/env python3
"""
Social Sentiment Module for Alpha Stock Finder V4
- WSB (WallStreetBets) data collection via Reddit JSON API
- Multi-source sentiment aggregation (StockTwits, Finviz)
- VADER + WSB-specific sentiment analysis
- Mention spike detection
- Ticker extraction from social media text

No PRAW dependency - uses Reddit's .json endpoint directly.
"""

import re
import json
import time
import sqlite3
import logging
import os
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

# VADER for social media sentiment
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False
    logging.warning("vaderSentiment not installed, using basic sentiment")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============ CONFIGURATION ============

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "social_data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "social_sentiment.db")

# Rate limiting
MIN_REQUEST_INTERVAL = 2.5  # seconds between Reddit requests
REDDIT_TIMEOUT = 15

# WSB subreddits to monitor
WSB_SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "options",
    "StockMarket",
    "thetagang",
]

# Common false positives that look like tickers
FALSE_POSITIVES = {
    "THE", "AND", "FOR", "NOT", "ARE", "BUT", "ALL", "CAN", "HAS", "HER",
    "WAS", "ONE", "OUR", "OUT", "DAY", "GET", "HIM", "HIS", "HOW", "ITS",
    "MAY", "NEW", "NOW", "OLD", "SEE", "WAY", "WHO", "DID", "LET", "SAY",
    "SHE", "TOO", "USE", "CEO", "CFO", "CTO", "MBA", "PHD", "USA", "UK",
    "EU", "GDP", "ETF", "YOLO", "DD", "ITM", "OTM", "ATM", "EOD", "IPO",
    "ATH", "FOMO", "FUD", "HOLD", "SELL", "BUY", "PUT", "CALL", "GOOD",
    "WILL", "BULL", "BEAR", "THEY", "OVER", "THIS", "MADE", "LIKE", "JUST",
    "MORE", "ONLY", "THAN", "STILL", "ALSO", "BACK", "COULD", "MAKE", "SOME",
    "VERY", "WHAT", "WHEN", "MUCH", "NEED", "REAL", "KNOW", "TAKE", "COME",
    "WANT", "MEAN", "GIVE", "WORK", "PART", "LONG", "LOOK", "HERE", "MOST",
    "EVEN", "BEEN", "HAVE", "THAT", "WITH", "FROM", "YOUR", "WERE", "THEM",
    "THEN", "INTO", "WENT", "MANY", "GOING", "WOULD", "BEFORE", "AFTER",
    "BEST", "WORST", "EVER", "NEVER", "ALWAYS", "ABOUT", "BEING", "WHERE",
    "WHICH", "THEIR", "THERE", "THESE", "THOSE", "OTHER", "FIRST", "LAST",
    "GREAT", "RIGHT", "UNDER", "AGAIN", "THINK", "AFTER", "BELOW", "ABOVE",
    "WELL", "SURE", "GOES", "DONE", "NEXT", "LAST", "LESS", "DUE", "PER",
    "BIG", "TOP", "SET", "RUN", "CUT", "ADD", "NET", "BIT", "GOT", "LOT",
    "FIX", "PAY", "AGE", "WAR", "LAW", "OIL", "GAS", "AIR", "SEA", "CAR",
    "MAP", "KEY", "TIP", "JOB", "FUN", "FIT", "RED", "HOT", "LOW", "TWO",
    "TEN", "SIX", "OWN", "USE", "ACT", "END", "OFF", "ANY", "HAD", "HAS",
    "HIS", "HOW", "ITS", "LET", "SAY", "SHE", "TOO", "USE", "WHO", "DID",
    "AM", "AN", "AT", "BE", "BY", "DO", "GO", "HE", "IF", "IN", "IS", "IT",
    "ME", "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US", "WE",
}

# Known valid tickers (popular + WSB favorites)
KNOWN_TICKERS = {
    # Tech giants
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA",
    # Semiconductors
    "AMD", "INTC", "QCOM", "AVGO", "TXN", "NXPI", "MU", "AMAT", "LRCX", "KLAC",
    "MRVL", "ON", "MCHP", "SWKS", "QRVO", "ENPH", "SEDG", "FSLR",
    # Software
    "CRM", "ORCL", "ADBE", "NOW", "SNOW", "PLTR", "MDB", "DDOG", "NET",
    "ZS", "CRWD", "PANW", "FTNT", "SNPS", "CDNS",
    # Fintech
    "V", "MA", "PYPL", "SQ", "COIN", "HOOD", "SOFI",
    # Streaming
    "NFLX", "DIS", "SPOT", "ROKU",
    # Healthcare
    "UNH", "JNJ", "PFE", "ABBV", "MRK", "LLY", "TMO", "ABT",
    # Finance
    "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW",
    # EV / Auto
    "RIVN", "LCID", "NIO", "F", "GM", "LI", "XPEV",
    # Meme / WSB favorites
    "GME", "AMC", "BB", "NOK", "SNDL", "EXPR", "KOSS", "MVIS", "BBBY",
    "SAVA", "CLNE", "PRPL", "MSTR", "BITO",
    # ETFs
    "SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV", "XLY",
    "GLD", "SLV", "TLT", "HYG", "VIX",
    # Crypto related
    "COIN", "MSTR", "RIOT", "CLSK", "HUT", "MARA", "BTBT",
    # AI theme
    "SMCI", "ARM", "AI", "SOUN", "BBAI", "RKLB", "IONQ", "RGTI", "QBTS", "LUNR",
    "RDDT", "SSTK", "WDC", "STX",
    # Consumer
    "AMZN", "TGT", "WMT", "COST", "HD", "MCD", "SBUX", "NKE", "LULU",
    # Energy
    "XOM", "CVX", "COP", "OXY", "SLB", "EOG", "PXD",
    # Industrials
    "CAT", "DE", "UNP", "HON", "GE", "BA", "LMT", "RTX",
    # Chinese ADR
    "BABA", "JD", "PDD", "BIDU", "NIO", "LI", "XPEV", "TME", "VIPS",
    # Other popular
    "ABNB", "RBLX", "UP", "OPEN", "UPST", "AFRM", "LC", "CRSR",
    "PTON", "ZM", "SNAP", "PINS", "TTD", "MDB",
    "U", "RKT", "LCID", "IONQ",
}

# WSB-specific sentiment keywords
BULLISH_KEYWORDS = [
    'moon', 'rocket', 'diamond', 'calls', 'buy', 'long', 'bullish', 'squeeze',
    'tendies', 'gain', 'profit', 'hodl', 'stonks', 'green', 'printer', 'print',
    'gamma', 'launch', 'liftoff', 'bounce', 'recovery', 'bottom', 'loading',
    'yolo', 'ape', 'apes', 'strong', 'diamondhands', 'w', 'win', 'bag',
    'to the moon', 'rip it', 'bang', 'space', 'going up', 'accumulating',
]

BEARISH_KEYWORDS = [
    'put', 'puts', 'short', 'bear', 'bearish', 'sell', 'selling', 'bagholder',
    'loss', 'red', 'down', 'crash', 'dump', 'bubble', 'overvalued', 'scam',
    'dead', 'margin', 'liquidated', 'paperhand', 'weak', 'capitulation',
    'tank', 'plunge', 'freefall', 'rip', 'funeral', 'rope',
]


# ============ TICKER EXTRACTION ============

class TickerExtractor:
    """Extract and validate stock tickers from social media text."""

    def __init__(self, known_tickers: Set[str] = None):
        self.known_tickers = known_tickers or KNOWN_TICKERS

    def extract(self, text: str) -> List[str]:
        """Extract tickers from text with multiple confidence levels."""
        found = set()

        # Pattern 1: $ prefixed (HIGHEST confidence - $TSLA, $GME)
        for match in re.finditer(r'\$([A-Z]{1,5})\b', text):
            ticker = match.group(1)
            if ticker not in FALSE_POSITIVES and len(ticker) >= 2:
                found.add(ticker)

        # Pattern 2: Financial context + uppercase (MEDIUM confidence)
        context_pattern = (
            r'(?:buying|selling|holding|shorting|calls?|puts?|shares?|stock|'
            r'position|price|average|sell|covered|assigned|exercised|leaps?|'
            r'wheel|squeeze|dip|stonk|options?)\s+([A-Z]{2,5})\b'
        )
        for match in re.finditer(context_pattern, text):
            ticker = match.group(1)
            if ticker not in FALSE_POSITIVES:
                found.add(ticker)

        # Pattern 3: Standalone uppercase 2-5 chars with known ticker validation
        for match in re.finditer(r'(?<![A-Za-z])([A-Z]{2,5})(?![A-Za-z])', text):
            ticker = match.group(1)
            if ticker not in FALSE_POSITIVES and ticker in self.known_tickers:
                found.add(ticker)

        return list(found)


# ============ SENTIMENT ANALYSIS ============

class SocialSentimentAnalyzer:
    """Analyze social media sentiment with WSB-specific signals."""

    def __init__(self):
        if VADER_AVAILABLE:
            self.vader = SentimentIntensityAnalyzer()
        else:
            self.vader = None

    def analyze(self, text: str) -> Dict:
        """Full sentiment analysis of social media text."""
        text_lower = text.lower()

        # VADER base sentiment
        if self.vader:
            vader_scores = self.vader.polarity_scores(text)
            vader_compound = vader_scores['compound']
        else:
            # Basic fallback: count positive/negative words
            vader_compound = 0.0

        # WSB-specific signals
        bullish_count = sum(1 for kw in BULLISH_KEYWORDS if kw in text_lower)
        bearish_count = sum(1 for kw in BEARISH_KEYWORDS if kw in text_lower)

        # Emoji signals
        rocket_count = text.count('\U0001f680')  # 🚀
        diamond_count = text.count('\U0001f4a8')  # 💎
        moon_count = text.count('\U0001f319') + text.count('\U0001f315')  # 🌙🌕

        # Position detection
        has_calls = bool(re.search(r'\b(calls?|call options?)\b', text_lower))
        has_puts = bool(re.search(r'\b(puts?|put options?)\b', text_lower))
        has_shares = bool(re.search(r'\b(shares?|long position)\b', text_lower))
        has_short = bool(re.search(r'\b(short|shorting|shorts?)\b', text_lower))

        # Combined WSB sentiment score
        wsb_score = (
            (bullish_count * 0.12 - bearish_count * 0.12) +
            (rocket_count * 0.15 + diamond_count * 0.08 + moon_count * 0.05) +
            vader_compound * 0.25
        )
        wsb_score = max(-1.0, min(1.0, wsb_score))

        # Label
        if wsb_score > 0.3:
            label = "bullish"
        elif wsb_score < -0.3:
            label = "bearish"
        else:
            label = "neutral"

        return {
            'vader_compound': vader_compound,
            'wsb_score': round(wsb_score, 3),
            'wsb_label': label,
            'bullish_keywords': bullish_count,
            'bearish_keywords': bearish_count,
            'rocket_emojis': rocket_count,
            'diamond_emojis': diamond_count,
            'has_calls': has_calls,
            'has_puts': has_puts,
            'has_shares': has_shares,
            'has_short': has_short,
            'position_hint': self._infer_position(
                has_calls, has_puts, has_shares, has_short, wsb_score
            ),
        }

    def _infer_position(self, calls, puts, shares, short, score):
        if calls and not puts:
            return "long_calls"
        elif puts and not calls:
            return "long_puts"
        elif short:
            return "short"
        elif shares:
            return "long_shares"
        elif score > 0.3:
            return "bullish_leaning"
        elif score < -0.3:
            return "bearish_leaning"
        return "unknown"

    def analyze_for_ticker(self, text: str, ticker: str) -> Dict:
        """Analyze sentiment specifically about a ticker (sentence-level)."""
        sentences = re.split(r'[.!?()\n]', text)
        ticker_sentences = [
            s.strip() for s in sentences
            if ticker in s.upper() or f'${ticker}' in s
        ]
        if ticker_sentences:
            focused_text = '. '.join(ticker_sentences)
            result = self.analyze(focused_text)
            result['focused_on_ticker'] = True
            result['relevant_sentences'] = len(ticker_sentences)
            return result
        return self.analyze(text)


# ============ REDDIT JSON API SCRAPER ============

class RedditJSONScraper:
    """Fetch WSB data via Reddit's .json endpoint (no PRAW required)."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "application/json",
        })
        self.last_request_time = 0
        self.min_interval = MIN_REQUEST_INTERVAL
        self.request_count = 0

    def _rate_limited_get(self, url: str) -> Optional[Dict]:
        """Make a rate-limited GET request to Reddit."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

        try:
            response = self.session.get(url, timeout=REDDIT_TIMEOUT)
            self.last_request_time = time.time()
            self.request_count += 1

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                logger.warning(f"Rate limited by Reddit. Waiting {retry_after}s...")
                time.sleep(retry_after)
                return self._rate_limited_get(url)
            else:
                logger.warning(f"HTTP {response.status_code} for {url}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            self.last_request_time = time.time()
            return None

    def get_subreddit_posts(self, subreddit: str, sort: str = "hot",
                            limit: int = 50, time_filter: str = "day") -> List[Dict]:
        """Fetch posts from a subreddit."""
        if sort == "top":
            url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}&t={time_filter}"
        else:
            url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}"

        data = self._rate_limited_get(url)
        if data and 'data' in data:
            return [self._parse_post(child['data']) for child in data['data']['children']
                    if child['kind'] == 't3']
        return []

    def get_post_comments(self, subreddit: str, post_id: str,
                          limit: int = 100) -> List[Dict]:
        """Fetch comments for a specific post."""
        url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json?limit={limit}"
        data = self._rate_limited_get(url)
        if data and len(data) > 1 and 'data' in data[1]:
            return self._parse_comments(data[1]['data']['children'])
        return []

    def search_subreddit(self, subreddit: str, query: str,
                         time_filter: str = "week", limit: int = 25) -> List[Dict]:
        """Search a subreddit for specific query."""
        import urllib.parse
        q = urllib.parse.quote(query)
        url = (f"https://www.reddit.com/r/{subreddit}/search.json"
               f"?q={q}&restrict_sr=on&t={time_filter}&limit={limit}&sort=relevance")
        data = self._rate_limited_get(url)
        if data and 'data' in data:
            return [self._parse_post(child['data']) for child in data['data']['children']
                    if child['kind'] == 't3']
        return []

    def _parse_post(self, post_data: Dict) -> Dict:
        """Parse a post from JSON API response."""
        return {
            'id': post_data.get('id', ''),
            'title': post_data.get('title', ''),
            'body': post_data.get('selftext', ''),
            'score': post_data.get('score', 0),
            'upvote_ratio': post_data.get('upvote_ratio', 0),
            'num_comments': post_data.get('num_comments', 0),
            'created_utc': post_data.get('created_utc', 0),
            'author': post_data.get('author', '[unknown]'),
            'url': post_data.get('url', ''),
            'permalink': post_data.get('permalink', ''),
            'link_flair_text': post_data.get('link_flair_text', ''),
            'fetched_at': time.time(),
        }

    def _parse_comments(self, children: List[Dict]) -> List[Dict]:
        """Parse comments from JSON API response."""
        comments = []
        for child in children:
            if child.get('kind') == 't1':
                data = child.get('data', {})
                comments.append({
                    'id': data.get('id', ''),
                    'body': data.get('body', ''),
                    'score': data.get('score', 0),
                    'created_utc': data.get('created_utc', 0),
                    'author': data.get('author', '[unknown]'),
                })
        return comments


# ============ ALTERNATIVE SENTIMENT SOURCES ============

class AlternativeSentimentSources:
    """Fetch sentiment from free alternative sources."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        self.last_request_time = 0
        self.min_interval = 3.0

    def _rate_limited_get(self, url: str, headers: Dict = None, timeout: int = 10) -> Optional[requests.Response]:
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        try:
            resp = self.session.get(url, headers=headers, timeout=timeout)
            self.last_request_time = time.time()
            return resp
        except requests.exceptions.RequestException:
            self.last_request_time = time.time()
            return None

    def get_stocktwits_sentiment(self, ticker: str) -> Optional[Dict]:
        """Get sentiment from StockTwits (free, no auth required).
        
        Note: StockTwits API no longer provides classified sentiment labels
        (Bullish/Bearish) in entities.sentiment. We now use VADER to analyze
        message text directly for sentiment scoring.
        """
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
        try:
            resp = self._rate_limited_get(url)
            if resp and resp.status_code == 200:
                data = resp.json()
                messages = data.get('messages', [])
                if not messages:
                    return None
                
                # VADER-based analysis since StockTwits dropped sentiment labels
                bullish = 0
                bearish = 0
                total_compound = 0.0
                analyzed = 0
                
                for m in messages:
                    body = m.get('body', '')
                    if not body:
                        continue
                    if VADER_AVAILABLE:
                        scores = SentimentIntensityAnalyzer().polarity_scores(body)
                        compound = scores['compound']
                        total_compound += compound
                        analyzed += 1
                        if compound >= 0.05:
                            bullish += 1
                        elif compound <= -0.05:
                            bearish += 1
                    else:
                        # Fallback: keyword-based
                        body_lower = body.lower()
                        has_bull = any(w in body_lower for w in ['buy', 'long', 'call', 'moon', 'bull', 'green', 'up'])
                        has_bear = any(w in body_lower for w in ['sell', 'short', 'put', 'bear', 'red', 'down', 'tank'])
                        if has_bull and not has_bear:
                            bullish += 1
                        elif has_bear and not has_bull:
                            bearish += 1
                        analyzed += 1
                
                avg_compound = round(total_compound / analyzed, 3) if analyzed > 0 else 0
                return {
                    'source': 'stocktwits',
                    'ticker': ticker,
                    'total_messages': len(messages),
                    'analyzed_messages': analyzed,
                    'bullish': bullish,
                    'bearish': bearish,
                    'sentiment_ratio': round(bullish / (bullish + bearish), 3) if (bullish + bearish) > 0 else 0.5,
                    'avg_compound': avg_compound,
                }
        except Exception as e:
            logger.debug(f"StockTwits error for {ticker}: {e}")
        return None

    def get_finviz_news_sentiment(self, ticker: str) -> Optional[Dict]:
        """Scrape news sentiment from Finviz."""
        from bs4 import BeautifulSoup
        url = f"https://finviz.com/quote.ashx?t={ticker}"
        try:
            resp = self._rate_limited_get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }, timeout=10)
            if resp and resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                news_table = soup.find("table", {"id": "news-table"})
                news_sentiment = 0
                news_count = 0
                if news_table:
                    for row in news_table.find_all("tr")[:10]:
                        link = row.find("a")
                        if link:
                            title = link.text.lower()
                            pos = any(w in title for w in
                                      ['upgrade', 'buy', 'bull', 'beat', 'rise', 'gain', 'positive', 'up'])
                            neg = any(w in title for w in
                                      ['downgrade', 'sell', 'bear', 'miss', 'fall', 'loss', 'negative', 'down'])
                            news_sentiment += (1 if pos else -1 if neg else 0)
                            news_count += 1
                return {
                    'source': 'finviz',
                    'ticker': ticker,
                    'news_count': news_count,
                    'news_sentiment': news_sentiment,
                    'news_label': 'bullish' if news_sentiment > 0 else 'bearish' if news_sentiment < 0 else 'neutral',
                }
        except Exception as e:
            logger.debug(f"Finviz error for {ticker}: {e}")
        return None

    def get_composite_sentiment(self, ticker: str) -> Dict:
        """Aggregate sentiment from all available sources."""
        results = {
            'ticker': ticker,
            'timestamp': datetime.now().isoformat(),
            'sources': {},
            'composite_score': 0,
            'confidence': 0,
        }

        scores = []
        weights = []

        # StockTwits
        st = self.get_stocktwits_sentiment(ticker)
        if st:
            results['sources']['stocktwits'] = st
            score = (st['sentiment_ratio'] - 0.5) * 2  # Normalize to [-1, 1]
            scores.append(score * 0.4)
            weights.append(0.4)

        # Finviz
        fv = self.get_finviz_news_sentiment(ticker)
        if fv:
            results['sources']['finviz'] = fv
            score = max(-1, min(1, fv['news_sentiment'] / 3))
            scores.append(score * 0.3)
            weights.append(0.3)

        if weights:
            results['composite_score'] = round(sum(scores) / sum(weights), 3)
            results['confidence'] = round(sum(weights), 2)

        return results


# ============ DATA STORAGE ============

class SocialDataStore:
    """SQLite-based storage for social sentiment data."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS reddit_posts (
            id TEXT PRIMARY KEY,
            subreddit TEXT,
            title TEXT,
            body TEXT,
            score INTEGER,
            upvote_ratio REAL,
            num_comments INTEGER,
            created_utc REAL,
            author TEXT,
            link_flair_text TEXT,
            fetched_at REAL
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS post_tickers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id TEXT,
            subreddit TEXT,
            ticker TEXT,
            wsb_score REAL,
            wsb_label TEXT,
            has_calls INTEGER,
            has_puts INTEGER,
            position_hint TEXT,
            FOREIGN KEY (post_id) REFERENCES reddit_posts(id)
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS ticker_daily (
            date TEXT,
            ticker TEXT,
            subreddit TEXT,
            mention_count INTEGER,
            avg_wsb_score REAL,
            total_engagement INTEGER,
            call_count INTEGER,
            put_count INTEGER,
            PRIMARY KEY (date, ticker, subreddit)
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS alt_sentiment (
            date TEXT,
            ticker TEXT,
            source TEXT,
            composite_score REAL,
            confidence REAL,
            raw_data TEXT,
            PRIMARY KEY (date, ticker, source)
        )''')

        # Indexes
        c.execute('CREATE INDEX IF NOT EXISTS idx_pt_ticker ON post_tickers(ticker)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_pt_date ON post_tickers(post_id, subreddit)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_rp_created ON reddit_posts(created_utc)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_td_date ON ticker_daily(date)')

        conn.commit()
        conn.close()

    def save_posts(self, posts: List[Dict], ticker_extractor: TickerExtractor,
                   sentiment_analyzer: SocialSentimentAnalyzer, subreddit: str):
        """Save posts with extracted tickers and sentiment."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        for post in posts:
            # Save post
            c.execute('''INSERT OR REPLACE INTO reddit_posts
                (id, subreddit, title, body, score, upvote_ratio, num_comments,
                 created_utc, author, link_flair_text, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (post['id'], subreddit, post['title'], post['body'],
                       post['score'], post.get('upvote_ratio', 0),
                       post.get('num_comments', 0), post['created_utc'],
                       post.get('author', ''), post.get('link_flair_text', ''),
                       post.get('fetched_at', time.time())))

            # Extract tickers and sentiment
            text = f"{post['title']} {post['body']}"
            tickers = ticker_extractor.extract(text)
            sentiment = sentiment_analyzer.analyze(text)

            for ticker in tickers:
                ticker_sent = sentiment_analyzer.analyze_for_ticker(text, ticker)
                c.execute('''INSERT INTO post_tickers
                    (post_id, subreddit, ticker, wsb_score, wsb_label,
                     has_calls, has_puts, position_hint)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                          (post['id'], subreddit, ticker,
                           ticker_sent['wsb_score'], ticker_sent['wsb_label'],
                           1 if ticker_sent['has_calls'] else 0,
                           1 if ticker_sent['has_puts'] else 0,
                           ticker_sent['position_hint']))

        conn.commit()
        conn.close()

    def get_ticker_mentions(self, ticker: str, days: int = 30) -> List[Dict]:
        """Get mention history for a ticker across all subreddits."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        c.execute('''SELECT date(p.created_utc, 'unixepoch') as day,
                     COUNT(*) as mentions, AVG(t.wsb_score) as avg_score
                     FROM post_tickers t JOIN reddit_posts p ON t.post_id = p.id
                     WHERE t.ticker = ? AND day >= ?
                     GROUP BY day ORDER BY day''', (ticker, since))

        result = [{'date': row[0], 'mentions': row[1], 'avg_score': round(row[2] or 0, 3)}
                  for row in c.fetchall()]
        conn.close()
        return result

    def get_daily_top_tickers(self, date: str = None, limit: int = 20) -> List[Dict]:
        """Get top mentioned tickers for a specific date."""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute('''SELECT t.ticker,
                     COUNT(*) as mentions,
                     AVG(t.wsb_score) as avg_score,
                     SUM(p.score) as total_engagement,
                     SUM(t.has_calls) as call_count,
                     SUM(t.has_puts) as put_count,
                     COUNT(DISTINCT t.subreddit) as subreddit_count
                     FROM post_tickers t JOIN reddit_posts p ON t.post_id = p.id
                     WHERE date(p.created_utc, 'unixepoch') = ?
                     GROUP BY t.ticker
                     ORDER BY mentions DESC LIMIT ?''', (date, limit))

        result = [{
            'ticker': row[0],
            'mentions': row[1],
            'avg_wsb_score': round(row[2] or 0, 3),
            'total_engagement': row[3],
            'calls': row[4],
            'puts': row[5],
            'call_put_ratio': round(row[4] / row[5], 2) if row[5] > 0 else 999,
            'subreddit_count': row[6],
        } for row in c.fetchall()]

        conn.close()
        return result

    def detect_mention_spikes(self, threshold: float = 3.0,
                              min_mentions: int = 3) -> List[Dict]:
        """Detect tickers with unusual mention volume.

        A spike = today's mentions >= threshold * average of past 7 days.
        """
        today = datetime.now().strftime('%Y-%m-%d')
        week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Today's mentions
        c.execute('''SELECT ticker, COUNT(*) as mentions
                     FROM post_tickers t JOIN reddit_posts p ON t.post_id = p.id
                     WHERE date(p.created_utc, 'unixepoch') = ?
                     GROUP BY ticker''', (today,))
        today_mentions = dict(c.fetchall())

        # Average mentions for past 7 days (excluding today)
        c.execute('''SELECT ticker, AVG(cnt) as avg_mentions
                     FROM (
                         SELECT t.ticker, date(p.created_utc, 'unixepoch') as day, COUNT(*) as cnt
                         FROM post_tickers t JOIN reddit_posts p ON t.post_id = p.id
                         WHERE date(p.created_utc, 'unixepoch') BETWEEN ? AND ?
                         GROUP BY t.ticker, day
                     ) GROUP BY ticker''', (week_ago, today))
        avg_mentions = {row[0]: row[1] for row in c.fetchall()}

        conn.close()

        spikes = []
        for ticker, today_count in today_mentions.items():
            if today_count < min_mentions:
                continue
            avg = avg_mentions.get(ticker, 1)
            spike_ratio = today_count / avg if avg > 0 else today_count
            if spike_ratio >= threshold:
                spikes.append({
                    'ticker': ticker,
                    'today_mentions': today_count,
                    'avg_mentions': round(avg, 1),
                    'spike_ratio': round(spike_ratio, 1),
                })

        return sorted(spikes, key=lambda x: x['spike_ratio'], reverse=True)

    def save_alt_sentiment(self, ticker: str, sentiment_data: Dict):
        """Save alternative source sentiment data."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        source = sentiment_data.get('source', 'composite')
        c.execute('''INSERT OR REPLACE INTO alt_sentiment
            (date, ticker, source, composite_score, confidence, raw_data)
            VALUES (?, ?, ?, ?, ?, ?)''',
                  (today, ticker, source,
                   sentiment_data.get('composite_score', 0),
                   sentiment_data.get('confidence', 0),
                   json.dumps(sentiment_data, default=str)))
        conn.commit()
        conn.close()


# ============ MAIN SOCIAL SENTIMENT ENGINE ============

class SocialSentimentEngine:
    """Complete social sentiment pipeline for Alpha Stock Finder V4."""

    def __init__(self):
        self.scraper = RedditJSONScraper()
        self.ticker_extractor = TickerExtractor()
        self.sentiment_analyzer = SocialSentimentAnalyzer()
        self.data_store = SocialDataStore()
        self.alt_sources = AlternativeSentimentSources()

    def _fetch_wsb_daily_threads(self) -> Dict:
        """Fetch WSB Daily Discussion and Daily Moves threads, extract comments as posts.

        WSB's daily discussion threads contain 10K+ comments with real-time
        ticker mentions and sentiment — the richest alpha source on Reddit.
        We treat each comment as a "post" for ticker extraction and sentiment.
        """
        daily_comments = 0
        threads_found = 0

        try:
            # Search for daily discussion threads (current week)
            dd_threads = self.scraper.search_subreddit(
                "wallstreetbets", "daily discussion", time_filter="week", limit=5
            )
            # Search for daily moves / what are your moves threads
            dm_threads = self.scraper.search_subreddit(
                "wallstreetbets", "what are your moves", time_filter="week", limit=3
            )

            # Merge and deduplicate by post id
            all_threads = dd_threads + dm_threads
            seen_ids = set()
            unique_threads = []
            for t in all_threads:
                if t['id'] not in seen_ids:
                    seen_ids.add(t['id'])
                    unique_threads.append(t)

            # Pick the most recent and most active thread (by comment count)
            # Sort by created_utc desc to get latest first
            unique_threads.sort(key=lambda x: x.get('created_utc', 0), reverse=True)

            # Fetch comments from top 2 most recent daily threads
            for thread in unique_threads[:2]:
                post_id = thread['id']
                title = thread.get('title', '')
                num_comments = thread.get('num_comments', 0)
                logger.info(f"  WSB daily thread: {title[:60]}... ({num_comments} comments)")

                try:
                    comments = self.scraper.get_post_comments(
                        "wallstreetbets", post_id, limit=200
                    )
                except Exception as e:
                    logger.warning(f"  Failed to fetch comments for {post_id}: {e}")
                    continue

                if not comments:
                    continue

                threads_found += 1

                # Convert comments to post-like format for save_posts
                comment_posts = []
                for c in comments:
                    if not c.get('body') or len(c.get('body', '')) < 5:
                        continue
                    comment_posts.append({
                        'id': f"{post_id}_c_{c['id']}",
                        'title': '',
                        'body': c['body'],
                        'score': c.get('score', 1),
                        'upvote_ratio': 0,
                        'num_comments': 0,
                        'created_utc': c.get('created_utc', 0),
                        'author': c.get('author', '[unknown]'),
                        'link_flair_text': 'daily_discussion',
                        'fetched_at': time.time(),
                    })

                # Save comments as posts in wallstreetbets_daily subreddit tag
                if comment_posts:
                    self.data_store.save_posts(
                        comment_posts, self.ticker_extractor,
                        self.sentiment_analyzer, "wallstreetbets"
                    )
                    daily_comments += len(comment_posts)
                    logger.info(f"  WSB daily: {len(comment_posts)} comments processed from '{title[:40]}'")

        except Exception as e:
            logger.error(f"Error fetching WSB daily threads: {e}")

        return {'daily_threads': threads_found, 'daily_comments': daily_comments}

    def fetch_wsb_data(self, limit_per_subreddit: int = 50) -> Dict:
        """Fetch data from all monitored subreddits."""
        all_posts = {}
        total_posts = 0

        for subreddit in WSB_SUBREDDITS:
            try:
                # Hot posts
                hot = self.scraper.get_subreddit_posts(subreddit, sort="hot", limit=limit_per_subreddit)
                # Rising posts
                rising = self.scraper.get_subreddit_posts(subreddit, sort="rising", limit=25)

                posts = hot + rising
                # Deduplicate
                seen = set()
                unique = []
                for p in posts:
                    if p['id'] not in seen:
                        seen.add(p['id'])
                        unique.append(p)

                self.data_store.save_posts(
                    unique, self.ticker_extractor, self.sentiment_analyzer, subreddit
                )
                all_posts[subreddit] = len(unique)
                total_posts += len(unique)
                logger.info(f"  r/{subreddit}: {len(unique)} posts fetched")

            except Exception as e:
                logger.error(f"Error fetching r/{subreddit}: {e}")
                all_posts[subreddit] = 0

        # Fetch WSB daily discussion thread comments (richest alpha source)
        daily_result = self._fetch_wsb_daily_threads()
        if daily_result['daily_comments'] > 0:
            all_posts['wallstreetbets_daily'] = daily_result['daily_comments']
            total_posts += daily_result['daily_comments']
            logger.info(f"  WSB daily threads: {daily_result['daily_threads']} threads, "
                       f"{daily_result['daily_comments']} comments")

        return {'total_posts': total_posts, 'per_subreddit': all_posts}

    def get_ticker_social_score(self, ticker: str) -> Dict:
        """Get comprehensive social sentiment score for a ticker.

        Returns a dict with:
        - wsb_mention_count: number of Reddit mentions today
        - wsb_sentiment: WSB-specific sentiment score [-1, 1]
        - mention_spike_ratio: ratio of today's mentions vs 7-day avg
        - alt_sentiment: composite score from alternative sources
        - social_signal: final combined social signal score [0, 100]
        """
        today = datetime.now().strftime('%Y-%m-%d')
        result = {
            'ticker': ticker,
            'wsb_mention_count': 0,
            'wsb_sentiment': 0,
            'mention_spike_ratio': 1.0,
            'alt_sentiment': 0,
            'social_signal': 50,  # default neutral
            'sources_available': [],
        }

        # 1. Reddit WSB data
        conn = sqlite3.connect(self.data_store.db_path)
        c = conn.cursor()

        c.execute('''SELECT COUNT(*), AVG(t.wsb_score), SUM(t.has_calls), SUM(t.has_puts)
                     FROM post_tickers t JOIN reddit_posts p ON t.post_id = p.id
                     WHERE t.ticker = ? AND date(p.created_utc, 'unixepoch') = ?''',
                  (ticker, today))
        row = c.fetchone()
        if row and row[0]:
            result['wsb_mention_count'] = row[0]
            result['wsb_sentiment'] = round(row[1] or 0, 3)
            result['call_count'] = row[2] or 0
            result['put_count'] = row[3] or 0
            result['sources_available'].append('reddit')

        conn.close()

        # 2. Mention spike detection
        mentions_history = self.data_store.get_ticker_mentions(ticker, days=7)
        if len(mentions_history) >= 2:
            # Average of past days (excluding today)
            past_mentions = [m['mentions'] for m in mentions_history[:-1]]
            if past_mentions:
                avg = sum(past_mentions) / len(past_mentions)
                today_count = result['wsb_mention_count']
                result['mention_spike_ratio'] = round(today_count / avg, 1) if avg > 0 else today_count

        # 3. Alternative sources (only for tickers with Reddit mentions to save API calls)
        # Only fetch StockTwits/Finviz for tickers that have at least 1 Reddit mention
        if result['wsb_mention_count'] >= 1:
            alt = self.alt_sources.get_composite_sentiment(ticker)
            if alt and alt.get('sources'):
                result['alt_sentiment'] = alt.get('composite_score', 0)
                result['alt_sources'] = alt.get('sources', {})
                for source in alt['sources']:
                    result['sources_available'].append(source)

        # 4. Calculate final social signal [0, 100]
        social_signal = 50  # neutral baseline

        # Reddit mentions contribution
        if result['wsb_mention_count'] > 0:
            # More mentions = more social attention
            mention_bonus = min(20, result['wsb_mention_count'] * 3)
            social_signal += mention_bonus

        # Sentiment direction
        if result['wsb_sentiment'] > 0.3:
            social_signal += 10
        elif result['wsb_sentiment'] < -0.3:
            social_signal -= 10

        # Spike detection bonus
        if result['mention_spike_ratio'] >= 3.0:
            social_signal += 15  # Strong spike
        elif result['mention_spike_ratio'] >= 2.0:
            social_signal += 8  # Moderate spike

        # Call/put ratio
        calls = result.get('call_count', 0)
        puts = result.get('put_count', 0)
        if calls + puts > 0:
            cp_ratio = calls / (calls + puts)
            if cp_ratio > 0.7:
                social_signal += 5  # Strong call bias = bullish
            elif cp_ratio < 0.3:
                social_signal -= 5  # Strong put bias = bearish

        # Alternative sources contribution
        if result['alt_sentiment'] != 0:
            social_signal += result['alt_sentiment'] * 10  # Scale [-1,1] to [-10,10]

        result['social_signal'] = max(0, min(100, round(social_signal, 1)))

        return result

    def get_daily_social_report(self) -> Dict:
        """Generate a comprehensive daily social sentiment report."""
        today = datetime.now().strftime('%Y-%m-%d')

        # Top mentioned tickers
        top_tickers = self.data_store.get_daily_top_tickers(date=today, limit=30)

        # Mention spikes
        spikes = self.data_store.detect_mention_spikes(threshold=2.5, min_mentions=2)

        # Social scores for top tickers
        social_scores = {}
        for t in top_tickers[:15]:
            score = self.get_ticker_social_score(t['ticker'])
            social_scores[t['ticker']] = score

        # Alternative sentiment for top 5
        alt_sentiments = {}
        for t in top_tickers[:5]:
            alt = self.alt_sources.get_composite_sentiment(t['ticker'])
            if alt:
                alt_sentiments[t['ticker']] = alt
                self.data_store.save_alt_sentiment(t['ticker'], alt)

        report = {
            'date': today,
            'timestamp': datetime.now().isoformat(),
            'top_tickers': top_tickers,
            'mention_spikes': spikes,
            'social_scores': social_scores,
            'alt_sentiments': alt_sentiments,
        }

        # Save report
        report_file = os.path.join(DATA_DIR, f"social_report_{today}.json")
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        return report

    def format_social_report(self, report: Dict) -> str:
        """Format social report for display/Telegram."""
        lines = [
            f"=== Social Sentiment Report: {report['date']} ===",
            "",
            "Top Mentioned Tickers on Reddit:",
        ]

        for i, t in enumerate(report.get('top_tickers', [])[:15], 1):
            score = t.get('avg_wsb_score', 0)
            emoji = "\U0001f534" if score < -0.3 else "\U0001f7e2" if score > 0.3 else "\U0001f7e1"
            cp = f"C/P:{t['call_put_ratio']}" if t.get('call_put_ratio', 999) < 999 else ""
            sub_count = t.get('subreddit_count', 0)
            lines.append(
                f" {i}. {t['ticker']} - {t['mentions']} mentions {emoji} "
                f"(score:{score:.2f} {cp} subs:{sub_count})"
            )

        if report.get('mention_spikes'):
            lines.append("")
            lines.append("Mention Spikes (unusual activity):")
            for spike in report['mention_spikes'][:5]:
                lines.append(
                    f"  {spike['ticker']}: {spike['today_mentions']} today "
                    f"({spike['spike_ratio']}x avg of {spike['avg_mentions']})"
                )

        # Social signal scores
        if report.get('social_scores'):
            lines.append("")
            lines.append("Social Signal Scores (0-100):")
            sorted_scores = sorted(
                report['social_scores'].items(),
                key=lambda x: x[1].get('social_signal', 50),
                reverse=True
            )
            for ticker, data in sorted_scores[:10]:
                signal = data.get('social_signal', 50)
                bar = "\u2588" * int(signal / 10) + "\u2591" * (10 - int(signal / 10))
                lines.append(f"  {ticker}: [{bar}] {signal}")

        return "\n".join(lines)


# ============ CLI ENTRY POINT ============

if __name__ == "__main__":
    import sys

    engine = SocialSentimentEngine()

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "fetch":
            print("Fetching social media data...")
            result = engine.fetch_wsb_data(limit_per_subreddit=50)
            print(f"Fetched {result['total_posts']} total posts")
            for sub, count in result['per_subreddit'].items():
                print(f"  r/{sub}: {count} posts")

        elif command == "report":
            report = engine.get_daily_social_report()
            print(engine.format_social_report(report))

        elif command == "ticker" and len(sys.argv) > 2:
            ticker = sys.argv[2].upper()
            score = engine.get_ticker_social_score(ticker)
            print(json.dumps(score, indent=2, default=str))

        elif command == "spikes":
            spikes = engine.data_store.detect_mention_spikes()
            if spikes:
                for s in spikes:
                    print(f"{s['ticker']}: {s['spike_ratio']}x spike "
                          f"({s['today_mentions']} today vs {s['avg_mentions']} avg)")
            else:
                print("No significant mention spikes detected")

        else:
            print("Usage: python social_sentiment.py [fetch|report|ticker SYMBOL|spikes]")
    else:
        # Default: fetch + report
        print("Fetching social media data...")
        engine.fetch_wsb_data(limit_per_subreddit=30)
        report = engine.get_daily_social_report()
        print("\n" + engine.format_social_report(report))
