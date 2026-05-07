#!/usr/bin/env python3
"""
Insider Trading Module for Alpha Stock Finder V4
Fetches SEC Form 4 insider trading data and detects cluster buying signals.

Data sources:
- SEC EDGAR RSS Feed: Latest Form 4 filings (atom XML)
- SEC EDGAR Full-Text Search: Search filings by company name
- SEC Form 4 XML: Parse actual filing for transaction details

Features:
- Fetch recent Form 4 filings via RSS feed
- Match filings to V4 ticker pool via company name / CIK / fuzzy match
- Parse Form 4 XML to extract transaction type (buy/sell), shares, price
- Detect cluster buying (2+ insider buys at same company)
- SQLite storage for historical filings
- 30-min cache TTL to avoid redundant API calls
- Rate limiting: 1s sleep between SEC API calls
"""

import re
import time
import sqlite3
import logging
import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
from html.parser import HTMLParser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============ CONFIGURATION ============

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "social_data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "social_sentiment.db")

# SEC EDGAR API endpoints
SEC_RSS_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=4&dateb=&owner=1&count=40&output=atom"
)
SEC_FULLTEXT_URL = "https://efts.sec.gov/LATEST/search-index"

# Rate limiting: minimum seconds between SEC API calls
SEC_MIN_INTERVAL = 1.0

# Cache TTL in seconds (30 minutes)
CACHE_TTL = 1800

# Atom XML namespace
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# ============ V4 TICKER POOL ============

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

# ============ COMPANY NAME TO TICKER MAPPING ============
# Static mapping of SEC-registered company names to tickers
# These are the exact names used in SEC filings (EDGAR)

COMPANY_NAME_TO_TICKER = {
    # Tech giants
    "APPLE INC": "AAPL",
    "MICROSOFT CORP": "MSFT",
    "ALPHABET INC": "GOOGL",
    "AMAZON COM INC": "AMZN",
    "META PLATFORMS INC": "META",
    "NVIDIA CORP": "NVDA",
    "TESLA INC": "TSLA",
    # Semiconductors
    "ADVANCED MICRO DEVICES INC": "AMD",
    "INTEL CORP": "INTC",
    "QUALCOMM INC": "QCOM",
    "BROADCOM INC": "AVGO",
    "TEXAS INSTRUMENTS INC": "TXN",
    "NXP SEMICONDUCTORS NV": "NXPI",
    "MICRON TECHNOLOGY INC": "MU",
    "APPLIED MATERIALS INC": "AMAT",
    "LAM RESEARCH CORP": "LRCX",
    "KLAC INC": "KLAC",
    "MARVELL TECHNOLOGY INC": "MRVL",
    "ON SEMICONDUCTOR CORP": "ON",
    "MICROCHIP TECHNOLOGY INC": "MCHP",
    "SKYWORKS SOLUTIONS INC": "SWKS",
    "ENPHASE ENERGY INC": "ENPH",
    "SOLAREDGE TECHNOLOGIES INC": "SEDG",
    # Software
    "SALESFORCE INC": "CRM",
    "ORACLE CORP": "ORCL",
    "ADOBE INC": "ADBE",
    "SERVICENOW INC": "NOW",
    "SNOWFLAKE INC": "SNOW",
    "PALANTIR TECHNOLOGIES INC": "PLTR",
    "MONGODB INC": "MDB",
    # Fintech
    "VISA INC": "V",
    "MASTERCARD INC": "MA",
    "PAYPAL HOLDINGS INC": "PYPL",
    "BLOCK INC": "SQ",
    "COINBASE GLOBAL INC": "COIN",
    "ROBINHOOD MARKETS INC": "HOOD",
    "SOFI TECHNOLOGIES INC": "SOFI",
    # Streaming / Media
    "NETFLIX INC": "NFLX",
    "WALT DISNEY CO": "DIS",
    "SPOTIFY TECHNOLOGY SA": "SPOT",
    # AI theme
    "SUPER MICRO COMPUTER INC": "SMCI",
    "ARM HOLDINGS PLC": "ARM",
    "C3 AI INC": "AI",
    "SOUNDHOUND AI INC": "SOUN",
    "BIGBEAR AI HOLDINGS INC": "BBAI",
    "ROCKET LAB USA INC": "RKLB",
    "IONQ INC": "IONQ",
    "RIGETTI COMPUTING INC": "RGTI",
    "D WAVE QUANTUM INC": "QBTS",
    # Meme / WSB favorites
    "GAMESTOP CORP": "GME",
    "AMC ENTERTAINMENT HOLDINGS INC": "AMC",
    "BLACKBERRY LTD": "BB",
    "RIVIAN AUTOMOTIVE INC": "RIVN",
    "LUCID GROUP INC": "LCID",
    "NIO INC": "NIO",
    # Other hot
    "REDDIT INC": "RDDT",
    "DATADOG INC": "DDOG",
    "ZSCALER INC": "ZS",
    "CROWDSTRIKE INC": "CRWD",
    "SHUTTERSTOCK INC": "SSTK",
    "WESTERN DIGITAL CORP": "WDC",
    "SEAGATE TECHNOLOGY HOLDINGS PLC": "STX",
    # Chinese ADR
    "ALIBABA GROUP HOLDING LTD": "BABA",
    "JD COM INC": "JD",
    "PDD HOLDINGS INC": "PDD",
    "BAIDU INC": "BIDU",
    # Crypto adjacent
    "MICROSTRATEGY INC": "MSTR",
    "RIOT PLATFORMS INC": "RIOT",
    "CLEANSPARK INC": "CLSK",
    "MARATHON DIGITAL HOLDINGS INC": "MARA",
}

# CIK to ticker mapping (top CIKs for V4 pool companies)
CIK_TO_TICKER = {
    "0000320193": "AAPL",
    "0000789019": "MSFT",
    "0001652044": "GOOGL",
    "0001018724": "AMZN",
    "0001326801": "META",
    "0001045810": "NVDA",
    "0001318605": "TSLA",
    "0000002488": "AMD",
    "0000050863": "INTC",
    "0000804751": "QCOM",
    "0000173076": "AVGO",
    "0000097476": "TXN",
    "0001410636": "NXPI",
    "0000723125": "MU",
    "0000007066": "AMAT",
    "0000759361": "LRCX",
    "0001065775": "KLAC",
    "0001411579": "MRVL",
    "0001283699": "ON",
    "0000898017": "MCHP",
    "0000813054": "SWKS",
    "0001440584": "ENPH",
    "0001411761": "SEDG",
    "0001108525": "CRM",
    "0001341439": "ORCL",
    "0000796343": "ADBE",
    "0001580540": "NOW",
    "0001640114": "SNOW",
    "0001813786": "PLTR",
    "0001604962": "MDB",
    "0001403161": "V",
    "0001393612": "MA",
    "0001633917": "PYPL",
    "0001808446": "SQ",
    "0001679788": "COIN",
    "0001783879": "HOOD",
    "0001818219": "SOFI",
    "0001065280": "NFLX",
    "0001001039": "DIS",
    "0001635093": "SPOT",
    "0001841166": "SMCI",
    "0001981856": "ARM",
    "0001554830": "AI",
    "0001829386": "SOUN",
    "0001818396": "BBAI",
    "0001814237": "RKLB",
    "0001818221": "IONQ",
    "0001839697": "RGTI",
    "0001840917": "QBTS",
    "0001326388": "GME",
    "0001410791": "AMC",
    "0000003161": "BB",
    "0001874178": "RIVN",
    "0001878228": "LCID",
    "0001738370": "NIO",
    "0002042338": "RDDT",
    "0001633098": "DDOG",
    "0001555130": "ZS",
    "0001534181": "CRWD",
    "0001383613": "SSTK",
    "0000100186": "WDC",
    "0001324313": "STX",
    "0001577552": "BABA",
    "0001544244": "JD",
    "0001768882": "PDD",
    "0001321943": "BIDU",
    "0001050446": "MSTR",
    "0001519791": "RIOT",
    "0001816602": "CLSK",
    "0001500805": "MARA",
}

# Transaction codes from Form 4
# P = Purchase (open market or private), A = Grant/exercise, D = Sale
BUY_TRANSACTION_CODES = {"P", "A", "C", "F"}  # P=Purchase, A=Grant, C=Conversion, F=Exercise
SELL_TRANSACTION_CODES = {"S", "D", "G"}  # S=Sale, D=Disposition, G=Gift

# For strict cluster buying detection, only count open-market purchases
OPEN_MARKET_BUY_CODES = {"P"}


# ============ HTML SUMMARY PARSER ============

class FilingSummaryParser(HTMLParser):
    """Parse the HTML summary in RSS <summary> to extract filing date and accession number."""

    def __init__(self):
        super().__init__()
        self.filed_date = None
        self.accession_number = None
        self._current_tag = None
        self._current_data = ""

    def handle_starttag(self, tag, attrs):
        if tag == "b":
            self._current_data = ""

    def handle_data(self, data):
        self._current_data += data

    def handle_endtag(self, tag):
        if tag == "b":
            text = self._current_data.strip().rstrip(":")
            self._current_tag = text


def parse_summary_html(html_text: str) -> Dict:
    """Extract filing date and accession number from RSS summary HTML.

    Example summary:
      <b>Filed:</b> 2026-04-24 <b>AccNo:</b> 0000902664-26-002148 <b>Size:</b> 12 KB
    """
    result = {"filed_date": None, "accession_number": None}

    if not html_text:
        return result

    # Extract Filed date
    filed_match = re.search(r"Filed:</b>\s*(\d{4}-\d{2}-\d{2})", html_text)
    if filed_match:
        result["filed_date"] = filed_match.group(1)

    # Extract AccNo
    accno_match = re.search(r"AccNo:</b>\s*([\w-]+)", html_text)
    if accno_match:
        result["accession_number"] = accno_match.group(1)

    return result


# ============ INSIDER TRADING FETCHER ============

class InsiderTradingFetcher:
    """Fetch SEC Form 4 insider trading data and detect cluster buying signals.

    Uses SEC EDGAR RSS feed for recent filings, full-text search for
    company-specific lookups, and Form 4 XML for transaction details.
    """

    def __init__(
        self,
        user_agent: str = "AlphaStockFinder/1.0 (deqiangm@gmail.com)",
        ticker_pool: List[str] = None,
    ):
        self.user_agent = user_agent
        self.headers = {"User-Agent": user_agent}
        self.ticker_pool: Set[str] = set(ticker_pool or V4_TICKERS)

        # Build lookup dicts
        self._name_to_ticker = self._build_name_lookup()
        self._cik_to_ticker = dict(CIK_TO_TICKER)

        # Cache for RSS results: (timestamp, data)
        self._cache_timestamp: Optional[float] = None
        self._cache_data: Optional[List[Dict]] = None

        # Rate limiting tracker
        self._last_request_time: float = 0.0

        # Initialize database
        self._init_db()

    def _build_name_lookup(self) -> Dict[str, str]:
        """Build a normalized company-name-to-ticker lookup dict.

        Includes all static mappings plus lowercase variants for flexibility.
        """
        lookup = {}
        for name, ticker in COMPANY_NAME_TO_TICKER.items():
            # Original uppercase
            lookup[name] = ticker
            # Stripped and normalized (remove trailing dots, commas, etc.)
            normalized = name.strip().upper().rstrip(".,")
            lookup[normalized] = ticker
            # Also without common suffixes like INC, CORP, etc. for fuzzy matching
            stripped = re.sub(
                r"\s+(INC|CORP|CORPORATION|LTD|LLC|CO|HOLDINGS|TECHNOLOGIES|GROUP|PLC|SA|NV)$",
                "",
                normalized,
            )
            if stripped != normalized:
                lookup[stripped] = ticker
        return lookup

    def _rate_limit(self):
        """Enforce minimum interval between SEC API requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < SEC_MIN_INTERVAL:
            time.sleep(SEC_MIN_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _sec_get(self, url: str, timeout: int = 20) -> Optional[requests.Response]:
        """Make a rate-limited GET request to SEC API with error handling."""
        self._rate_limit()
        try:
            resp = requests.get(url, headers=self.headers, timeout=timeout)
            if resp.status_code == 429:
                logger.warning("SEC rate limit hit (429), backing off 5s")
                time.sleep(5)
                resp = requests.get(url, headers=self.headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            logger.error(f"SEC API request failed: {url} -> {e}")
            return None

    def _init_db(self):
        """Create insider_filings table in SQLite if not exists."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS insider_filings (
            accession_number TEXT PRIMARY KEY,
            filing_date TEXT,
            reporter_name TEXT,
            reporter_cik TEXT,
            company_name TEXT,
            ticker TEXT,
            issuer_cik TEXT,
            transaction_type TEXT,
            transaction_code TEXT,
            shares REAL,
            price_per_share REAL,
            total_value REAL,
            is_open_market INTEGER DEFAULT 0,
            is_director INTEGER DEFAULT 0,
            is_officer INTEGER DEFAULT 0,
            link TEXT,
            xml_url TEXT,
            fetched_at REAL,
            parsed_at REAL
        )''')

        # Indexes for common queries
        c.execute('CREATE INDEX IF NOT EXISTS idx_if_ticker ON insider_filings(ticker)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_if_date ON insider_filings(filing_date)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_if_type ON insider_filings(transaction_type)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_if_company ON insider_filings(company_name)')

        conn.commit()
        conn.close()
        logger.debug("insider_filings table initialized")

    # ============ RSS FEED PARSING ============

    def fetch_recent_filings(self, hours: int = 24) -> List[Dict]:
        """Fetch Form 4 filings from the last N hours via SEC RSS feed.

        The RSS feed returns the latest 40 Form 4 filings per request.
        Returns paired entries (reporter + issuer merged into one record).

        Args:
            hours: Lookback window in hours (default 24).

        Returns:
            List of filing dicts with keys:
                filing_date, reporter_name, company_name, ticker,
                cik, transaction_type, link, accession_number
        """
        # Check cache first
        if self._cache_data is not None and self._cache_timestamp is not None:
            cache_age = time.time() - self._cache_timestamp
            if cache_age < CACHE_TTL:
                logger.info(f"Using cached RSS data ({cache_age:.0f}s old)")
                return self._filter_by_hours(self._cache_data, hours)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        raw_entries = []

        # Fetch first page
        url = SEC_RSS_URL
        page = 0
        max_pages = 10

        while url and page < max_pages:
            resp = self._sec_get(url)
            if resp is None:
                break

            try:
                root = ET.fromstring(resp.text)
            except ET.ParseError as e:
                logger.error(f"Failed to parse RSS XML: {e}")
                break

            entries = root.findall("atom:entry", ATOM_NS)
            if not entries:
                break

            page_has_recent = False

            for entry in entries:
                filing = self._parse_rss_entry(entry)
                if filing is None:
                    continue

                # No dedup here -- both Reporter and Issuer entries share the
                # same link and need to be collected for later pairing.
                # Dedup happens after pairing by link in _pair_rss_filings.

                # Check if filing is within the time window
                filing_dt = self._parse_filing_datetime(filing)
                if filing_dt and filing_dt >= cutoff:
                    page_has_recent = True
                    raw_entries.append(filing)

            if not page_has_recent and raw_entries:
                break

            # Check for next page link
            next_link = None
            for link_elem in root.findall("atom:link", ATOM_NS):
                if link_elem.get("rel") == "next":
                    next_link = link_elem.get("href")
                    break

            if next_link:
                url = next_link
                page += 1
            else:
                break

        # Pair Reporting + Issuer entries by index page link
        paired = self._pair_rss_filings(raw_entries)

        # Filter by time window again after pairing
        result = self._filter_by_hours(paired, hours)

        # Update cache
        self._cache_data = paired
        self._cache_timestamp = time.time()

        logger.info(f"Fetched {len(result)} paired Form 4 filings from last {hours}h")
        return result

    def _parse_rss_entry(self, entry) -> Optional[Dict]:
        """Parse a single RSS feed entry into a filing dict.

        The RSS feed alternates entries for each filing:
        - Entry 1: '4 - Reporter Name (CIK) (Reporting)'
        - Entry 2: '4 - Company Name (CIK) (Issuer)'

        Both share the same link and filing date. We pair them up.
        """
        try:
            title_elem = entry.find("atom:title", ATOM_NS)
            if title_elem is None or not title_elem.text:
                return None
            title = title_elem.text.strip()

            link_elem = entry.find("atom:link", ATOM_NS)
            link = link_elem.get("href", "") if link_elem is not None else ""

            summary_elem = entry.find("atom:summary", ATOM_NS)
            summary_html = summary_elem.text if summary_elem is not None and summary_elem.text else ""

            updated_elem = entry.find("atom:updated", ATOM_NS)
            updated = updated_elem.text if updated_elem is not None else ""

            # Parse summary for filed date and accession number
            summary_info = parse_summary_html(summary_html)
            filed_date = summary_info.get("filed_date") or ""
            accession_number = summary_info.get("accession_number") or ""

            # Fallback: try to extract accession number from link
            if not accession_number and link:
                acc_match = re.search(r"(\d{10}-\d{2}-\d{6})", link)
                if acc_match:
                    accession_number = acc_match.group(1)

            # Parse title: "4 - Name (CIK) (Role)"
            # Role is either "Reporting" (the insider) or "Issuer" (the company)
            title_match = re.match(
                r"^4\s*-\s*(.+?)\s*\((\d+)\)\s*\((Reporting|Issuer)\)$", title
            )
            if not title_match:
                return None

            name = title_match.group(1).strip()
            cik = title_match.group(2).strip()
            role = title_match.group(3).strip()

            filing = {
                "filing_date": filed_date,
                "updated": updated,
                "accession_number": accession_number,
                "link": link,
                "reporter_name": "",
                "reporter_cik": "",
                "company_name": "",
                "issuer_cik": "",
                "ticker": None,
                "transaction_type": None,  # Will be determined by XML parsing
            }

            if role == "Reporting":
                filing["reporter_name"] = name
                filing["reporter_cik"] = cik
            elif role == "Issuer":
                filing["company_name"] = name
                filing["issuer_cik"] = cik
                # Try to match ticker
                filing["ticker"] = self._match_ticker(name, cik)

            return filing

        except Exception as e:
            logger.warning(f"Error parsing RSS entry: {e}")
            return None

    def _pair_rss_filings(self, raw_entries: List[Dict]) -> List[Dict]:
        """Pair Reporting and Issuer entries that share the same filing.

        The RSS feed produces separate entries for the reporter and the issuer.
        They share the same accession number but have different link URLs
        (the CIK embedded in the URL path differs: reporter CIK vs issuer CIK).
        So we group by accession number and merge fields.
        """
        # Group by accession number (unique per filing)
        by_accession: Dict[str, Dict] = {}

        for entry in raw_entries:
            acc = entry.get("accession_number", "")
            if not acc:
                # Try to extract accession from link
                link = entry.get("link", "")
                acc_match = re.search(r"(\d{10}-\d{2}-\d{6})", link)
                acc = acc_match.group(1) if acc_match else ""
            if not acc:
                continue

            if acc not in by_accession:
                by_accession[acc] = {
                    "filing_date": "",
                    "updated": "",
                    "accession_number": acc,
                    "link": "",
                    "reporter_name": "",
                    "reporter_cik": "",
                    "company_name": "",
                    "issuer_cik": "",
                    "ticker": None,
                    "transaction_type": None,
                }

            merged = by_accession[acc]

            # Merge fields (prefer non-empty values)
            for key in ["filing_date", "updated"]:
                if entry.get(key) and not merged.get(key):
                    merged[key] = entry[key]

            # Prefer the Issuer entry's link (has issuer CIK in path)
            if entry.get("company_name") and entry.get("link"):
                merged["link"] = entry["link"]

            # Also set link from first entry if not yet set
            if not merged["link"] and entry.get("link"):
                merged["link"] = entry["link"]

            if entry.get("reporter_name"):
                merged["reporter_name"] = entry["reporter_name"]
                merged["reporter_cik"] = entry.get("reporter_cik", "")

            if entry.get("company_name"):
                merged["company_name"] = entry["company_name"]
                merged["issuer_cik"] = entry.get("issuer_cik", "")
                merged["ticker"] = entry.get("ticker")

            # If we still don't have a ticker but have company name or CIK, try matching
            if not merged["ticker"] and merged.get("company_name"):
                merged["ticker"] = self._match_ticker(
                    merged["company_name"], merged.get("issuer_cik", "")
                )

        return list(by_accession.values())

    def _filter_by_hours(self, filings: List[Dict], hours: int) -> List[Dict]:
        """Filter filings to only those within the last N hours."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = []
        for f in filings:
            filing_dt = self._parse_filing_datetime(f)
            if filing_dt and filing_dt >= cutoff:
                result.append(f)
            elif not filing_dt:
                # If we can't parse the date, include it anyway (better to over-include)
                result.append(f)
        return result

    def _parse_filing_datetime(self, filing: Dict) -> Optional[datetime]:
        """Parse filing date/time from a filing dict. Returns UTC datetime or None."""
        # Try 'updated' field first (more precise, includes time)
        updated = filing.get("updated", "")
        if updated:
            try:
                # Format: 2026-04-24T21:35:59-04:00
                dt = datetime.fromisoformat(updated)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except (ValueError, TypeError):
                pass

        # Fallback: filing_date (just date, no time)
        filed_date = filing.get("filing_date", "")
        if filed_date:
            try:
                dt = datetime.strptime(filed_date, "%Y-%m-%d")
                return dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass

        return None

    # ============ TICKER MATCHING ============

    def _match_ticker(self, company_name: str, cik: str = "") -> Optional[str]:
        """Match a SEC company name + CIK to a ticker in our pool.

        Matching priority:
        1. CIK cross-reference (most reliable)
        2. Direct name match (exact or normalized)
        3. Fuzzy match on company name (last resort)

        Args:
            company_name: Company name from SEC filing (e.g. 'NVIDIA CORP')
            cik: CIK number from SEC filing (e.g. '0001045810')

        Returns:
            Ticker symbol if matched, None otherwise.
        """
        if not company_name and not cik:
            return None

        # 1. CIK match (most reliable)
        if cik:
            # Try with leading zeros (SEC uses 10-digit CIK)
            padded_cik = cik.zfill(10)
            if padded_cik in self._cik_to_ticker:
                ticker = self._cik_to_ticker[padded_cik]
                if ticker in self.ticker_pool:
                    return ticker
            # Also try without leading zeros
            stripped_cik = cik.lstrip("0") or "0"
            for stored_cik, ticker in self._cik_to_ticker.items():
                if stored_cik.lstrip("0") == stripped_cik and ticker in self.ticker_pool:
                    return ticker

        if not company_name:
            return None

        # Normalize company name for matching
        normalized = company_name.strip().upper().rstrip(".,")

        # 2. Direct name match
        if normalized in self._name_to_ticker:
            ticker = self._name_to_ticker[normalized]
            if ticker in self.ticker_pool:
                return ticker

        # Also try with common variations
        # Remove suffixes like INC, CORP, LTD, etc.
        stripped = re.sub(
            r"\s+(INC|CORP|CORPORATION|LTD|LLC|CO|HOLDINGS|TECHNOLOGIES|GROUP|PLC|SA|NV|LP|L P)$",
            "",
            normalized,
        )
        if stripped in self._name_to_ticker:
            ticker = self._name_to_ticker[stripped]
            if ticker in self.ticker_pool:
                return ticker

        # 3. Fuzzy match: check if any pool company name contains the key words
        # This handles cases like "NVIDIA CORP /DE/" or "Apple Inc." with punctuation
        ticker = self._fuzzy_match_ticker(normalized)
        if ticker:
            return ticker

        return None

    def _fuzzy_match_ticker(self, normalized_name: str) -> Optional[str]:
        """Fuzzy match a normalized company name to a ticker.

        Strategy: Check if the company name's key words appear in any
        of our known company names. We use word-level matching to handle
        minor differences like punctuation, abbreviations, etc.

        Args:
            normalized_name: Uppercase, stripped company name.

        Returns:
            Ticker symbol if matched, None otherwise.
        """
        # Extract key words (skip very short words and common suffixes)
        skip_words = {
            "INC", "CORP", "CORPORATION", "LTD", "LLC", "CO", "THE",
            "HOLDINGS", "TECHNOLOGIES", "TECHNOLOGY", "GROUP", "PLC",
            "SA", "NV", "LP", "L", "P", "DE", "OF", "AND", "FOR",
        }
        name_words = set(
            w for w in normalized_name.split()
            if len(w) > 1 and w not in skip_words
        )

        if not name_words:
            return None

        best_match = None
        best_score = 0

        for known_name, ticker in COMPANY_NAME_TO_TICKER.items():
            if ticker not in self.ticker_pool:
                continue

            known_words = set(
                w for w in known_name.split()
                if len(w) > 1 and w not in skip_words
            )
            if not known_words:
                continue

            # Calculate word overlap score
            common = name_words & known_words
            if not common:
                continue

            # Score: ratio of common words to total unique words
            score = len(common) / max(len(name_words), len(known_words))

            if score > best_score and score >= 0.5:
                best_score = score
                best_match = ticker

        return best_match

    # ============ FORM 4 XML PARSING ============

    def parse_form4_xml(self, filing_url: str) -> Dict:
        """Parse an actual Form 4 XML filing to extract transaction details.

        Fetches the filing index page, finds the XML document, then parses it
        for transaction type (buy/sell), shares, and price.

        NOTE: This is best-effort. Returns partial data if XML parse fails.

        Args:
            filing_url: URL to the filing index page on SEC EDGAR.

        Returns:
            Dict with keys: transaction_type, transaction_code, shares,
            price_per_share, total_value, is_open_market, is_director,
            is_officer, reporter_name, company_name, ticker, error
        """
        result = {
            "transaction_type": None,
            "transaction_code": None,
            "shares": None,
            "price_per_share": None,
            "total_value": None,
            "is_open_market": False,
            "is_director": False,
            "is_officer": False,
            "reporter_name": None,
            "company_name": None,
            "ticker": None,
            "error": None,
        }

        try:
            # Step 1: Find the XML file URL from the filing index
            xml_url = self._find_form4_xml_url(filing_url)
            if not xml_url:
                result["error"] = "Could not find Form 4 XML URL"
                return result

            # Step 2: Fetch and parse the XML
            resp = self._sec_get(xml_url)
            if resp is None:
                result["error"] = f"Failed to fetch XML from {xml_url}"
                return result

            # Handle potential encoding issues
            content = resp.content
            try:
                xml_text = content.decode("utf-8")
            except UnicodeDecodeError:
                xml_text = content.decode("latin-1", errors="replace")

            # Remove XML processing instruction if present (can cause issues)
            xml_text = re.sub(r'<\?xml[^?]*\?>', '', xml_text).strip()

            root = ET.fromstring(xml_text)

            # Parse issuer info
            issuer = root.find(".//issuer")
            if issuer is not None:
                issuer_name = issuer.findtext("issuerName", "").strip()
                issuer_cik = issuer.findtext("issuerCik", "").strip()
                issuer_symbol = issuer.findtext("issuerTradingSymbol", "").strip().upper()
                result["company_name"] = issuer_name
                result["ticker"] = issuer_symbol if issuer_symbol in self.ticker_pool else None

                # Try CIK match if ticker not in pool
                if not result["ticker"] and issuer_cik:
                    result["ticker"] = self._cik_to_ticker.get(
                        issuer_cik.zfill(10), None
                    )

            # Parse reporting owner
            owner = root.find(".//reportingOwner")
            if owner is not None:
                result["reporter_name"] = (
                    owner.findtext(".//rptOwnerName", "").strip()
                )
                # Check director/officer status
                is_director = owner.findtext(".//isDirector", "0").strip()
                is_officer = owner.findtext(".//isOfficer", "0").strip()
                result["is_director"] = is_director == "1"
                result["is_officer"] = is_officer == "1"

            # Parse non-derivative transactions
            non_deriv_table = root.find(".//nonDerivativeTable")
            if non_deriv_table is not None:
                transactions = non_deriv_table.findall(
                    ".//nonDerivativeTransaction"
                )
                if transactions:
                    # Use the first transaction (most relevant)
                    txn = transactions[0]
                    result = self._parse_transaction(txn, result)

            # If no non-derivative transactions, try derivative table
            if result["transaction_type"] is None:
                deriv_table = root.find(".//derivativeTable")
                if deriv_table is not None:
                    deriv_txns = deriv_table.findall(".//derivativeTransaction")
                    if deriv_txns:
                        txn = deriv_txns[0]
                        result = self._parse_derivative_transaction(txn, result)

        except ET.ParseError as e:
            result["error"] = f"XML parse error: {e}"
            logger.warning(f"Form 4 XML parse error for {filing_url}: {e}")
        except Exception as e:
            result["error"] = f"Unexpected error: {e}"
            logger.warning(f"Form 4 parse error for {filing_url}: {e}")

        return result

    def _parse_transaction(self, txn, result: Dict) -> Dict:
        """Parse a nonDerivativeTransaction element into result dict."""
        # Transaction code
        txn_code = txn.findtext(".//transactionCode", "").strip()
        result["transaction_code"] = txn_code

        # Determine buy/sell
        if txn_code in OPEN_MARKET_BUY_CODES:
            result["transaction_type"] = "buy"
            result["is_open_market"] = txn_code == "P"
        elif txn_code in SELL_TRANSACTION_CODES:
            result["transaction_type"] = "sell"
        else:
            # Unknown code, try acquired/disposed code
            acq_disp = txn.findtext(
                ".//transactionAcquiredDisposedCode/value", ""
            ).strip()
            if acq_disp == "A":
                result["transaction_type"] = "buy"
            elif acq_disp == "D":
                result["transaction_type"] = "sell"

        # Shares
        shares_text = txn.findtext(".//transactionShares/value", "")
        try:
            result["shares"] = float(shares_text.replace(",", "")) if shares_text else None
        except (ValueError, AttributeError):
            pass

        # Price per share
        price_text = txn.findtext(".//transactionPricePerShare/value", "")
        try:
            result["price_per_share"] = float(price_text.replace(",", "")) if price_text else None
        except (ValueError, AttributeError):
            pass

        # Total value
        if result["shares"] and result["price_per_share"]:
            result["total_value"] = result["shares"] * result["price_per_share"]

        return result

    def _parse_derivative_transaction(self, txn, result: Dict) -> Dict:
        """Parse a derivativeTransaction element (e.g. option exercise)."""
        txn_code = txn.findtext(".//transactionCode", "").strip()
        result["transaction_code"] = txn_code

        if txn_code in BUY_TRANSACTION_CODES:
            result["transaction_type"] = "buy"
        elif txn_code in SELL_TRANSACTION_CODES:
            result["transaction_type"] = "sell"

        # Shares (underlying securities)
        shares_text = txn.findtext(
            ".//underlyingSecurityShares/value", ""
        ) or txn.findtext(".//transactionShares/value", "")
        try:
            result["shares"] = float(shares_text.replace(",", "")) if shares_text else None
        except (ValueError, AttributeError):
            pass

        return result

    def _find_form4_xml_url(self, filing_url: str) -> Optional[str]:
        """Find the Form 4 XML document URL from a filing index page.

        The filing_url points to the index.htm page. We need to find
        the actual XML file. Two approaches:
        1. Convert index.htm URL to the directory JSON listing
        2. Parse the index page HTML for XML links

        Args:
            filing_url: SEC filing index page URL.

        Returns:
            Full URL to the Form 4 XML file, or None.
        """
        # Strategy 1: Use SEC directory listing API
        # Convert: .../0000902664-26-002148-index.htm
        #     to:  .../000090266426002148/index.json
        try:
            # Extract CIK and accession from URL
            url_match = re.search(
                r"/edgar/data/(\d+)/([\d-]+)/", filing_url
            )
            if url_match:
                cik = url_match.group(1)
                acc_with_dashes = url_match.group(2)
                acc_no_dashes = acc_with_dashes.replace("-", "")

                # Build directory listing URL
                dir_url = (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{cik}/{acc_no_dashes}/index.json"
                )

                resp = self._sec_get(dir_url)
                if resp is not None:
                    try:
                        dir_data = resp.json()
                        for item in dir_data.get("directory", {}).get("item", []):
                            name = item.get("name", "")
                            if name.endswith(".xml") and "form4" in name.lower():
                                return (
                                    f"https://www.sec.gov/Archives/edgar/data/"
                                    f"{cik}/{acc_no_dashes}/{name}"
                                )
                            # Also accept any .xml file in a Form 4 filing
                            if name.endswith(".xml") and not name.startswith("000"):
                                return (
                                    f"https://www.sec.gov/Archives/edgar/data/"
                                    f"{cik}/{acc_no_dashes}/{name}"
                                )
                    except (ValueError, KeyError):
                        pass

            # Strategy 2: Try common XML naming patterns
            if url_match:
                cik = url_match.group(1)
                acc_with_dashes = url_match.group(2)
                acc_no_dashes = acc_with_dashes.replace("-", "")

                # Common patterns: primary_doc.xml or wk-form4_*.xml
                base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no_dashes}"

                # Try the accession-based filename
                candidate_urls = [
                    f"{base}/{acc_with_dashes}.xml",
                    f"{base}/primary_doc.xml",
                ]
                for candidate in candidate_urls:
                    resp = self._sec_get(candidate)
                    if resp is not None and resp.status_code == 200:
                        content_type = resp.headers.get("Content-Type", "")
                        if "xml" in content_type or resp.text.strip().startswith("<"):
                            return candidate

        except Exception as e:
            logger.warning(f"Error finding Form 4 XML URL: {e}")

        return None

    # ============ CLUSTER BUYING DETECTION ============

    def detect_cluster_buying(self, filings: List[Dict]) -> List[Dict]:
        """Detect cluster buying: 2+ insider buys at the same company.

        Cluster buying is a strong bullish signal when multiple insiders
        buy around the same time, especially if they are directors/officers.

        Args:
            filings: List of filing dicts (from fetch_recent_filings or DB).

        Returns:
            List of cluster dicts sorted by signal_strength (descending):
                ticker, buy_count, total_insiders, signal_strength (0-100),
                reporters (list of reporter names)
        """
        # Group filings by ticker, only for tickers in our pool
        ticker_filings: Dict[str, List[Dict]] = defaultdict(list)

        for filing in filings:
            ticker = filing.get("ticker")
            if not ticker or ticker not in self.ticker_pool:
                continue

            txn_type = filing.get("transaction_type")
            if txn_type == "buy":
                ticker_filings[ticker].append(filing)

        # Find clusters (2+ buys)
        clusters = []
        for ticker, buy_filings in ticker_filings.items():
            if len(buy_filings) < 2:
                continue

            # Unique reporters
            reporters = list(set(
                f.get("reporter_name", "Unknown") for f in buy_filings
            ))

            # Count insiders vs total transactions
            total_insiders = len(reporters)
            buy_count = len(buy_filings)

            # Calculate signal strength (0-100)
            signal_strength = self._calculate_cluster_signal(
                buy_count=buy_count,
                total_insiders=total_insiders,
                filings=buy_filings,
            )

            cluster = {
                "ticker": ticker,
                "buy_count": buy_count,
                "total_insiders": total_insiders,
                "signal_strength": signal_strength,
                "reporters": reporters,
                "total_value": sum(
                    f.get("total_value", 0) or 0 for f in buy_filings
                ),
                "company_name": buy_filings[0].get("company_name", ""),
            }
            clusters.append(cluster)

        # Sort by signal strength descending
        clusters.sort(key=lambda x: x["signal_strength"], reverse=True)
        return clusters

    def _calculate_cluster_signal(
        self, buy_count: int, total_insiders: int, filings: List[Dict]
    ) -> float:
        """Calculate cluster buying signal strength (0-100).

        Factors:
        - Number of unique insiders buying (more = stronger signal)
        - Number of transactions (more = stronger signal)
        - Whether buys are open-market (P code = stronger signal)
        - Whether buyers are directors/officers (stronger signal)
        - Total value of purchases (larger = stronger signal)

        Returns:
            Signal strength as a float 0-100.
        """
        score = 0.0

        # Factor 1: Number of unique insiders (0-30 points)
        # 2 insiders = 15, 3 = 22, 4+ = 30
        if total_insiders >= 4:
            score += 30
        elif total_insiders == 3:
            score += 22
        elif total_insiders == 2:
            score += 15
        else:
            score += 5

        # Factor 2: Number of buy transactions (0-20 points)
        # More transactions = more conviction
        if buy_count >= 5:
            score += 20
        elif buy_count >= 3:
            score += 14
        elif buy_count >= 2:
            score += 10
        else:
            score += 3

        # Factor 3: Open-market purchases (0-25 points)
        # P code = open market buy (strongest signal)
        open_market_count = sum(
            1 for f in filings
            if f.get("is_open_market") or f.get("transaction_code") == "P"
        )
        if open_market_count >= 3:
            score += 25
        elif open_market_count >= 2:
            score += 18
        elif open_market_count >= 1:
            score += 10
        else:
            score += 3

        # Factor 4: Director/Officer involvement (0-25 points)
        insider_buyers = sum(
            1 for f in filings
            if f.get("is_director") or f.get("is_officer")
        )
        if insider_buyers >= 3:
            score += 25
        elif insider_buyers >= 2:
            score += 18
        elif insider_buyers >= 1:
            score += 10
        else:
            score += 3

        return min(100.0, max(0.0, score))

    # ============ SINGLE TICKER SIGNAL ============

    def get_insider_signal(self, ticker: str) -> Dict:
        """Get insider trading signal for a single ticker.

        Fetches recent filings, parses them, and generates a composite
        insider signal.

        Args:
            ticker: Stock ticker symbol (e.g. 'NVDA').

        Returns:
            Dict with keys: signal, score, details
                signal: 'bullish' | 'bearish' | 'neutral'
                score: float from -100 (bearish) to +100 (bullish)
                details: dict with buy_count, sell_count, cluster, etc.
        """
        ticker = ticker.upper()
        if ticker not in self.ticker_pool:
            return {
                "signal": "neutral",
                "score": 0.0,
                "details": {"error": f"{ticker} not in ticker pool"},
            }

        # Try to get filings from DB first, then fetch new ones
        db_filings = self._get_filings_from_db(ticker, days=7)
        if db_filings:
            filings = db_filings
        else:
            # Fetch recent filings and filter for this ticker
            all_filings = self.fetch_recent_filings(hours=168)  # 7 days
            filings = [f for f in all_filings if f.get("ticker") == ticker]

            # If no RSS data for this ticker, try full-text search
            if not filings:
                filings = self._search_filings_by_ticker(ticker)

        # Parse any unparsed filings to get transaction types
        parsed_filings = []
        for filing in filings:
            if filing.get("transaction_type") is None and filing.get("link"):
                # Parse the actual Form 4 XML
                parsed = self.parse_form4_xml(filing["link"])
                filing["transaction_type"] = parsed.get("transaction_type")
                filing["transaction_code"] = parsed.get("transaction_code")
                filing["shares"] = parsed.get("shares")
                filing["price_per_share"] = parsed.get("price_per_share")
                filing["total_value"] = parsed.get("total_value")
                filing["is_open_market"] = parsed.get("is_open_market", False)
                filing["is_director"] = parsed.get("is_director", False)
                filing["is_officer"] = parsed.get("is_officer", False)

                # Save parsed data to DB
                self._save_filing(filing)

            parsed_filings.append(filing)

        # Count buys and sells
        buy_count = sum(1 for f in parsed_filings if f.get("transaction_type") == "buy")
        sell_count = sum(1 for f in parsed_filings if f.get("transaction_type") == "sell")
        unknown_count = sum(
            1 for f in parsed_filings if f.get("transaction_type") is None
        )

        # Calculate signal score (-100 to +100)
        if buy_count + sell_count == 0:
            return {
                "signal": "neutral",
                "score": 0.0,
                "details": {
                    "ticker": ticker,
                    "buy_count": 0,
                    "sell_count": 0,
                    "unknown_count": unknown_count,
                    "total_filings": len(parsed_filings),
                    "cluster": None,
                    "note": "No buy/sell data available",
                },
            }

        # Net insider activity score
        net = buy_count - sell_count
        total = buy_count + sell_count
        raw_score = (net / total) * 50  # Scale to -50 to +50

        # Bonus for cluster buying
        cluster = None
        if buy_count >= 2:
            clusters = self.detect_cluster_buying(parsed_filings)
            for c in clusters:
                if c["ticker"] == ticker:
                    cluster = c
                    # Cluster bonus: up to +50
                    raw_score += cluster["signal_strength"] * 0.5
                    break

        # Clamp to -100..+100
        score = max(-100.0, min(100.0, raw_score))

        # Determine signal label
        if score >= 30:
            signal_label = "bullish"
        elif score <= -30:
            signal_label = "bearish"
        else:
            signal_label = "neutral"

        return {
            "signal": signal_label,
            "score": round(score, 1),
            "details": {
                "ticker": ticker,
                "buy_count": buy_count,
                "sell_count": sell_count,
                "unknown_count": unknown_count,
                "total_filings": len(parsed_filings),
                "cluster": cluster,
                "buy_value": sum(
                    f.get("total_value", 0) or 0
                    for f in parsed_filings
                    if f.get("transaction_type") == "buy"
                ),
                "sell_value": sum(
                    f.get("total_value", 0) or 0
                    for f in parsed_filings
                    if f.get("transaction_type") == "sell"
                ),
            },
        }

    def _search_filings_by_ticker(self, ticker: str) -> List[Dict]:
        """Search SEC full-text search API for Form 4 filings by ticker.

        This is a fallback when the RSS feed doesn't have recent filings
        for a specific ticker.

        Args:
            ticker: Stock ticker symbol.

        Returns:
            List of filing dicts.
        """
        # Find the company name from our lookup
        company_name = None
        for name, t in COMPANY_NAME_TO_TICKER.items():
            if t == ticker:
                company_name = name
                break

        if not company_name:
            logger.warning(f"No company name found for ticker {ticker}")
            return []

        # Search SEC full-text index
        query = f'"{company_name}"'
        url = (
            f"{SEC_FULLTEXT_URL}"
            f"?q={requests.utils.quote(query)}"
            f"&forms=4&dateRange=7d&size=20"
        )

        resp = self._sec_get(url)
        if resp is None:
            return []

        try:
            data = resp.json()
        except ValueError:
            return []

        filings = []
        seen = set()

        for hit in data.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            display_names = src.get("display_names", [])
            file_date = src.get("file_date", "")
            adsh = src.get("adsh", "")

            if adsh in seen:
                continue
            seen.add(adsh)

            # Extract reporter and issuer from display_names
            reporter_name = ""
            reporter_cik = ""
            issuer_name = ""
            issuer_cik = ""

            for dn in display_names:
                # Parse: "NVIDIA CORP (NVDA) (CIK 0001045810)" or "Dabiri John (CIK 0001818224)"
                cik_match = re.search(r"\(CIK\s+(\d+)\)", dn)
                cik = cik_match.group(1) if cik_match else ""

                # Check if this is the issuer (has ticker symbol)
                ticker_match = re.search(r"\(([A-Z]+)\)", dn)
                if ticker_match and ticker_match.group(1) == ticker:
                    # This is the issuer entry
                    name_part = re.sub(r"\s*\(CIK\s+\d+\)", "", dn)
                    name_part = re.sub(r"\s*\([A-Z]+\)", "", name_part).strip()
                    issuer_name = name_part
                    issuer_cik = cik
                elif cik:
                    # This is the reporter
                    name_part = re.sub(r"\s*\(CIK\s+\d+\)", "", dn).strip()
                    reporter_name = name_part
                    reporter_cik = cik

            # Build filing link from adsh and issuer CIK
            link = ""
            if issuer_cik and adsh:
                acc_no_dashes = adsh.replace("-", "")
                link = (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{issuer_cik.lstrip('0')}/{acc_no_dashes}/"
                    f"{adsh}-index.htm"
                )

            filing = {
                "filing_date": file_date,
                "updated": "",
                "accession_number": adsh,
                "link": link,
                "reporter_name": reporter_name,
                "reporter_cik": reporter_cik,
                "company_name": issuer_name,
                "issuer_cik": issuer_cik,
                "ticker": ticker,
                "transaction_type": None,  # Needs XML parsing
            }
            filings.append(filing)

        logger.info(
            f"Full-text search found {len(filings)} Form 4 filings for {ticker}"
        )
        return filings

    # ============ DATABASE OPERATIONS ============

    def _save_filing(self, filing: Dict):
        """Save a filing to the SQLite database.

        Uses INSERT OR REPLACE to handle duplicates by accession_number.
        """
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()

            c.execute('''INSERT OR REPLACE INTO insider_filings
                (accession_number, filing_date, reporter_name, reporter_cik,
                 company_name, ticker, issuer_cik, transaction_type,
                 transaction_code, shares, price_per_share, total_value,
                 is_open_market, is_director, is_officer, link, xml_url,
                 fetched_at, parsed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    filing.get("accession_number", ""),
                    filing.get("filing_date", ""),
                    filing.get("reporter_name", ""),
                    filing.get("reporter_cik", ""),
                    filing.get("company_name", ""),
                    filing.get("ticker", ""),
                    filing.get("issuer_cik", ""),
                    filing.get("transaction_type"),
                    filing.get("transaction_code"),
                    filing.get("shares"),
                    filing.get("price_per_share"),
                    filing.get("total_value"),
                    1 if filing.get("is_open_market") else 0,
                    1 if filing.get("is_director") else 0,
                    1 if filing.get("is_officer") else 0,
                    filing.get("link", ""),
                    filing.get("xml_url", ""),
                    filing.get("fetched_at", time.time()),
                    filing.get("parsed_at", time.time() if filing.get("transaction_type") else None),
                ))

            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"DB error saving filing: {e}")

    def _save_filings_batch(self, filings: List[Dict]):
        """Save multiple filings to the database."""
        for filing in filings:
            self._save_filing(filing)

    def _get_filings_from_db(self, ticker: str, days: int = 7) -> List[Dict]:
        """Get filings for a ticker from the database.

        Args:
            ticker: Stock ticker symbol.
            days: Lookback window in days.

        Returns:
            List of filing dicts.
        """
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()

            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=days)
            ).strftime("%Y-%m-%d")

            c.execute(
                '''SELECT * FROM insider_filings
                   WHERE ticker = ? AND filing_date >= ?
                   ORDER BY filing_date DESC''',
                (ticker, cutoff),
            )

            rows = c.fetchall()
            conn.close()

            result = []
            for row in rows:
                result.append({
                    "accession_number": row["accession_number"],
                    "filing_date": row["filing_date"],
                    "reporter_name": row["reporter_name"],
                    "reporter_cik": row["reporter_cik"],
                    "company_name": row["company_name"],
                    "ticker": row["ticker"],
                    "issuer_cik": row["issuer_cik"],
                    "transaction_type": row["transaction_type"],
                    "transaction_code": row["transaction_code"],
                    "shares": row["shares"],
                    "price_per_share": row["price_per_share"],
                    "total_value": row["total_value"],
                    "is_open_market": bool(row["is_open_market"]),
                    "is_director": bool(row["is_director"]),
                    "is_officer": bool(row["is_officer"]),
                    "link": row["link"],
                })

            return result

        except sqlite3.Error as e:
            logger.error(f"DB error reading filings for {ticker}: {e}")
            return []

    def get_all_cached_tickers(self) -> List[str]:
        """Get all tickers that have cached insider filings in the DB."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT DISTINCT ticker FROM insider_filings WHERE ticker != ''")
            rows = c.fetchall()
            conn.close()
            return [row[0] for row in rows]
        except sqlite3.Error:
            return []

    # ============ HIGH-LEVEL SCAN ============

    def scan_insider_activity(self, hours: int = 24, parse_xml: bool = False) -> Dict:
        """Run a full insider activity scan for the V4 ticker pool.

        This is the main entry point for integration with alpha_scanner_v4.

        Args:
            hours: Lookback window in hours.
            parse_xml: If True, parse actual Form 4 XML for transaction
                       details (slower but more accurate). Default: False.

        Returns:
            Dict with keys:
                total_filings: int
                pool_filings: int (filings matching V4 tickers)
                clusters: list of cluster buying signals
                ticker_signals: dict of ticker -> insider signal
                scan_time: float (seconds)
        """
        start = time.time()

        # Fetch recent filings
        filings = self.fetch_recent_filings(hours=hours)

        # Filter for V4 pool tickers
        pool_filings = [f for f in filings if f.get("ticker") in self.ticker_pool]

        logger.info(
            f"Insider scan: {len(filings)} total filings, "
            f"{len(pool_filings)} matching V4 pool"
        )

        # Optionally parse XML for transaction details
        if parse_xml and pool_filings:
            logger.info(f"Parsing Form 4 XML for {len(pool_filings)} pool filings...")
            for filing in pool_filings:
                if filing.get("link") and filing.get("transaction_type") is None:
                    parsed = self.parse_form4_xml(filing["link"])
                    filing["transaction_type"] = parsed.get("transaction_type")
                    filing["transaction_code"] = parsed.get("transaction_code")
                    filing["shares"] = parsed.get("shares")
                    filing["price_per_share"] = parsed.get("price_per_share")
                    filing["total_value"] = parsed.get("total_value")
                    filing["is_open_market"] = parsed.get("is_open_market", False)
                    filing["is_director"] = parsed.get("is_director", False)
                    filing["is_officer"] = parsed.get("is_officer", False)

        # Save to DB
        self._save_filings_batch(pool_filings)

        # Detect cluster buying
        clusters = self.detect_cluster_buying(pool_filings)

        # Generate per-ticker signals
        ticker_signals = {}
        for ticker in self.ticker_pool:
            ticker_pool_filings = [
                f for f in pool_filings if f.get("ticker") == ticker
            ]
            if ticker_pool_filings:
                buy_count = sum(
                    1 for f in ticker_pool_filings
                    if f.get("transaction_type") == "buy"
                )
                sell_count = sum(
                    1 for f in ticker_pool_filings
                    if f.get("transaction_type") == "sell"
                )
                ticker_signals[ticker] = {
                    "total": len(ticker_pool_filings),
                    "buys": buy_count,
                    "sells": sell_count,
                }

        scan_time = time.time() - start

        return {
            "total_filings": len(filings),
            "pool_filings": len(pool_filings),
            "clusters": clusters,
            "ticker_signals": ticker_signals,
            "scan_time": round(scan_time, 2),
        }


# ============ CLI ENTRY POINT ============

if __name__ == "__main__":
    import sys

    fetcher = InsiderTradingFetcher()

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "fetch":
            hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
            print(f"Fetching Form 4 filings from last {hours}h...")
            filings = fetcher.fetch_recent_filings(hours=hours)
            print(f"Found {len(filings)} filings")
            # Show V4 pool matches
            pool_filings = [f for f in filings if f.get("ticker")]
            if pool_filings:
                print(f"\nV4 Pool matches ({len(pool_filings)}):")
                for f in pool_filings:
                    print(
                        f"  {f.get('ticker', '?'):6s} | "
                        f"{f.get('reporter_name', 'Unknown'):30s} | "
                        f"{f.get('company_name', '?'):30s} | "
                        f"{f.get('filing_date', '?')}"
                    )
            else:
                print("No V4 pool matches in recent filings")

        elif command == "cluster":
            hours = int(sys.argv[2]) if len(sys.argv) > 2 else 168
            print(f"Detecting cluster buying (last {hours}h)...")
            filings = fetcher.fetch_recent_filings(hours=hours)
            clusters = fetcher.detect_cluster_buying(filings)
            if clusters:
                for c in clusters:
                    print(
                        f"\n  {c['ticker']}: {c['buy_count']} buys "
                        f"by {c['total_insiders']} insiders "
                        f"(signal: {c['signal_strength']:.0f}/100)"
                    )
                    for r in c["reporters"]:
                        print(f"    - {r}")
            else:
                print("No cluster buying detected")

        elif command == "signal" and len(sys.argv) > 2:
            ticker = sys.argv[2].upper()
            print(f"Getting insider signal for {ticker}...")
            signal = fetcher.get_insider_signal(ticker)
            print(f"  Signal: {signal['signal']} (score: {signal['score']})")
            print(f"  Details: {signal['details']}")

        elif command == "scan":
            hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
            parse_xml = "--parse" in sys.argv
            print(f"Running full insider scan (last {hours}h, parse_xml={parse_xml})...")
            result = fetcher.scan_insider_activity(hours=hours, parse_xml=parse_xml)
            print(f"  Total filings: {result['total_filings']}")
            print(f"  Pool filings: {result['pool_filings']}")
            print(f"  Scan time: {result['scan_time']}s")
            if result["clusters"]:
                print(f"\n  Cluster buying signals ({len(result['clusters'])}):")
                for c in result["clusters"]:
                    print(
                        f"    {c['ticker']}: {c['buy_count']} buys, "
                        f"signal={c['signal_strength']:.0f}/100"
                    )
            if result["ticker_signals"]:
                print(f"\n  Ticker activity ({len(result['ticker_signals'])}):")
                for t, s in sorted(
                    result["ticker_signals"].items(),
                    key=lambda x: x[1]["total"],
                    reverse=True,
                ):
                    print(
                        f"    {t}: {s['total']} filings "
                        f"({s['buys']} buys, {s['sells']} sells)"
                    )

        elif command == "parse" and len(sys.argv) > 2:
            url = sys.argv[2]
            print(f"Parsing Form 4 XML from: {url}")
            result = fetcher.parse_form4_xml(url)
            for k, v in result.items():
                if v is not None:
                    print(f"  {k}: {v}")

        else:
            print("Usage: python insider_trading.py [fetch|cluster|signal|scan|parse]")
            print("  fetch [HOURS]              - Fetch recent Form 4 filings")
            print("  cluster [HOURS]            - Detect cluster buying")
            print("  signal TICKER              - Get insider signal for ticker")
            print("  scan [HOURS] [--parse]     - Full insider activity scan")
            print("  parse URL                  - Parse a Form 4 XML filing")

    else:
        # Default: quick fetch + report
        print("Fetching recent Form 4 filings (24h)...")
        filings = fetcher.fetch_recent_filings(hours=24)
        pool_filings = [f for f in filings if f.get("ticker")]
        print(f"  {len(filings)} total filings, {len(pool_filings)} V4 pool matches")

        if pool_filings:
            print("\nV4 Pool insider filings:")
            for f in pool_filings[:20]:
                txn = f.get("transaction_type", "?")
                print(
                    f"  {f.get('ticker', '?'):6s} | "
                    f"{f.get('reporter_name', 'Unknown')[:30]:30s} | "
                    f"txn={txn:5s} | "
                    f"{f.get('filing_date', '?')}"
                )
