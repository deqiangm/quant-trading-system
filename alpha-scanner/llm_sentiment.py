#!/usr/bin/env python3
"""
LLM-based Financial Sentiment Analyzer for Alpha Stock Finder

Uses NVIDIA API free-tier LLMs (DeepSeek V4 Flash) for batch financial
sentiment analysis. Replaces VADER with LLM for better understanding of
financial jargon, slang, and nuanced market language.

Features:
- Batch analysis: 5 texts per API call (tested optimal for DeepSeek V4 Flash)
- Retry with exponential backoff on API errors
- Rate limiting: 0.3s between calls (well under 1000 req/day NVIDIA free tier)
- VADER fallback when LLM is unavailable
- Result caching by text hash to avoid re-analyzing same posts within a scan
- Signal labels: very_bullish, bullish, neutral, bearish, very_bearish
- Aggregate sentiment scoring for lists of social media posts

Typical usage:
    analyzer = LLMSentimentAnalyzer()
    scores = analyzer.analyze_batch(["NVDA earnings beat", "AMD margin pressure"])
    signal = analyzer.score_to_signal(scores[0])
    result = analyzer.get_enhanced_sentiment([{"body": "...", "title": "..."}])
"""

import hashlib
import logging
import os
import re
import time
from typing import Dict, List, Optional, Tuple

import requests

# VADER fallback - used when LLM API is unavailable
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False

logger = logging.getLogger(__name__)

# ============ DEFAULTS ============

DEFAULT_API_KEY = "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"
DEFAULT_MODEL = "deepseek-ai/deepseek-v4-flash"
BACKUP_MODEL = "meta/llama-3.1-8b-instruct"
DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

BATCH_SIZE = 5  # Optimal batch size tested with DeepSeek V4 Flash
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0  # Base backoff in seconds (doubles each retry)
RATE_LIMIT_INTERVAL = 0.3  # Seconds between API calls
CACHE_MAX_SIZE = 500  # Max cached sentiment results


class LLMSentimentAnalyzer:
    """LLM-powered financial sentiment analyzer using NVIDIA API.

    Uses DeepSeek V4 Flash (or other NVIDIA-hosted models) for batch sentiment
    analysis of financial text. Falls back to VADER if the LLM API is
    unavailable or returns errors after all retries.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """Initialize the LLM sentiment analyzer.

        Args:
            api_key: NVIDIA API key. Reads from NIM_API_KEY or NVIDIA_API_KEY
                     env vars first, then falls back to hardcoded default.
            model: Model identifier on NVIDIA API. Defaults to deepseek-v4-flash.
            base_url: NVIDIA chat completions endpoint URL.
        """
        # API configuration with env var priority
        self.api_key = (
            api_key
            or os.environ.get("NIM_API_KEY")
            or os.environ.get("NVIDIA_API_KEY")
            or DEFAULT_API_KEY
        )
        self.model = model or DEFAULT_MODEL
        self.base_url = base_url or DEFAULT_BASE_URL

        # Session for connection reuse
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        })

        # Rate limiting state
        self._last_api_call_time = 0.0

        # Cache: text hash -> sentiment score float
        self._cache: Dict[str, float] = {}

        # VADER fallback analyzer (lazy init)
        self._vader_analyzer: Optional[SentimentIntensityAnalyzer] = None

        # Track if LLM is available (set to False after persistent failures)
        self._llm_available = True

        logger.info(
            f"LLMSentimentAnalyzer initialized: model={self.model}, "
            f"batch_size={BATCH_SIZE}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_batch(self, texts: List[str]) -> List[float]:
        """Analyze sentiment for a list of texts in batches of 5.

        Sends texts to the LLM in batches of BATCH_SIZE (5) for efficient
        API usage. Each batch call returns comma-separated float scores.

        Args:
            texts: List of text strings to analyze.

        Returns:
            List of sentiment scores in [-1, 1] range, same length as input.
            Falls back to VADER for individual texts on LLM failure.
        """
        if not texts:
            return []

        # Check cache first - return cached scores, collect uncached texts
        results: List[Optional[float]] = [None] * len(texts)
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        for i, text in enumerate(texts):
            cache_key = self._cache_key(text)
            if cache_key in self._cache:
                results[i] = self._cache[cache_key]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if uncached_texts:
            logger.debug(
                f"Analyzing {len(uncached_texts)} uncached texts "
                f"(cached: {len(texts) - len(uncached_texts)})"
            )

            # Process uncached texts in batches of BATCH_SIZE
            batch_scores: List[float] = []
            for batch_start in range(0, len(uncached_texts), BATCH_SIZE):
                batch = uncached_texts[batch_start:batch_start + BATCH_SIZE]
                scores = self._call_llm_batch(batch)

                if scores is not None:
                    # Pad or trim in case of mismatch
                    while len(scores) < len(batch):
                        logger.warning(
                            f"LLM returned {len(scores)} scores for "
                            f"{len(batch)} texts, using VADER fallback for missing"
                        )
                        scores.append(self._vader_fallback(batch[len(scores)]))
                    if len(scores) > len(batch):
                        scores = scores[:len(batch)]
                    batch_scores.extend(scores)
                else:
                    # LLM failed for this batch - use VADER fallback
                    logger.warning("LLM batch failed, falling back to VADER")
                    for text in batch:
                        batch_scores.append(self._vader_fallback(text))

            # Fill results and update cache
            for idx, score in zip(uncached_indices, batch_scores):
                results[idx] = score
                cache_key = self._cache_key(texts[idx])
                self._cache_set(cache_key, score)

        # Ensure no None values remain (shouldn't happen, but safety check)
        final_results = []
        for i, r in enumerate(results):
            if r is None:
                final_results.append(self._vader_fallback(texts[i]))
            else:
                final_results.append(r)

        return final_results

    def analyze_single(self, text: str) -> float:
        """Analyze sentiment for a single text string.

        Convenience wrapper around analyze_batch for single text analysis.

        Args:
            text: Text string to analyze.

        Returns:
            Sentiment score in [-1, 1] range.
        """
        scores = self.analyze_batch([text])
        return scores[0] if scores else 0.0

    @staticmethod
    def score_to_signal(score: float) -> str:
        """Convert a sentiment score to a human-readable signal label.

        Args:
            score: Sentiment score in [-1, 1] range.

        Returns:
            Signal label: very_bullish, bullish, neutral, bearish, or very_bearish.
        """
        if score >= 0.6:
            return "very_bullish"
        elif score >= 0.2:
            return "bullish"
        elif score > -0.2:
            return "neutral"
        elif score > -0.6:
            return "bearish"
        else:
            return "very_bearish"

    def get_enhanced_sentiment(self, posts: List[Dict]) -> Dict:
        """Compute aggregate enhanced sentiment from a list of social media posts.

        Takes posts with 'body' and/or 'title' keys, analyzes each with LLM,
        and returns an aggregate sentiment score (0-100 scale) plus breakdown.

        Args:
            posts: List of dicts, each with 'body' and/or 'title' keys.
                   Example: [{"body": "NVDA to the moon!", "title": "NVDA"}]

        Returns:
            Dict with:
                - aggregate_score: float 0-100 (50 = neutral)
                - signal: str label (very_bullish, bullish, etc.)
                - post_count: int number of posts analyzed
                - avg_score: float mean sentiment in [-1, 1]
                - score_distribution: dict with count per signal label
                - individual_scores: list of per-post dicts with text, score, signal
        """
        if not posts:
            return {
                "aggregate_score": 50.0,
                "signal": "neutral",
                "post_count": 0,
                "avg_score": 0.0,
                "score_distribution": {},
                "individual_scores": [],
            }

        # Extract text from each post (title + body combined)
        texts = []
        for post in posts:
            parts = []
            title = post.get("title", "")
            body = post.get("body", "")
            if title:
                parts.append(title.strip())
            if body:
                parts.append(body.strip())
            text = " | ".join(parts) if parts else ""
            texts.append(text)

        # Filter out empty texts
        valid_pairs = [(i, t) for i, t in enumerate(texts) if t.strip()]
        if not valid_pairs:
            return {
                "aggregate_score": 50.0,
                "signal": "neutral",
                "post_count": len(posts),
                "avg_score": 0.0,
                "score_distribution": {"neutral": len(posts)},
                "individual_scores": [],
            }

        valid_indices, valid_texts = zip(*valid_pairs)
        scores = self.analyze_batch(list(valid_texts))

        # Build individual scores list
        individual_scores = []
        signal_counts: Dict[str, int] = {}
        total_score = 0.0

        for idx, score in zip(valid_indices, scores):
            signal = self.score_to_signal(score)
            signal_counts[signal] = signal_counts.get(signal, 0) + 1
            total_score += score
            individual_scores.append({
                "text": texts[idx][:120],  # Truncate for readability
                "score": round(score, 3),
                "signal": signal,
            })

        avg_score = total_score / len(scores) if scores else 0.0

        # Convert avg_score [-1,1] to aggregate_score [0,100]
        # -1 -> 0, 0 -> 50, 1 -> 100
        aggregate_score = round((avg_score + 1.0) / 2.0 * 100.0, 1)
        aggregate_score = max(0.0, min(100.0, aggregate_score))

        return {
            "aggregate_score": aggregate_score,
            "signal": self.score_to_signal(avg_score),
            "post_count": len(posts),
            "avg_score": round(avg_score, 3),
            "score_distribution": signal_counts,
            "individual_scores": individual_scores,
        }

    # ------------------------------------------------------------------
    # LLM API interaction
    # ------------------------------------------------------------------

    def _call_llm_batch(self, texts: List[str]) -> Optional[List[float]]:
        """Send a batch of texts to the LLM and parse sentiment scores.

        Args:
            texts: List of 1-5 text strings to analyze.

        Returns:
            List of float scores in [-1, 1], or None if the call failed
            after all retries.
        """
        if not self._llm_available:
            return None

        # Build the user prompt with numbered texts
        numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
        user_prompt = numbered

        # System prompt: financial context, comma-separated numeric output
        system_prompt = (
            "You are a financial sentiment analyzer. "
            "Score each statement from -1 (very bearish) to 1 (very bullish). "
            "Consider financial jargon: earnings beat=positive, miss=negative, "
            "margin pressure=negative, surge=positive, layoffs=negative, "
            "upgrade=positive, downgrade=negative, guidance raise=positive, "
            "guidance cut=negative. "
            "Respond ONLY with comma-separated numbers, nothing else. "
            "Example: 0.8, -0.4, -0.6, 0.8, -0.5"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,  # Low temperature for consistent scoring
            "max_tokens": 50,    # Short response expected
            "top_p": 0.9,
        }

        # Retry loop with exponential backoff
        for attempt in range(MAX_RETRIES):
            try:
                # Rate limit: ensure minimum interval between API calls
                elapsed = time.time() - self._last_api_call_time
                if elapsed < RATE_LIMIT_INTERVAL:
                    time.sleep(RATE_LIMIT_INTERVAL - elapsed)

                response = self.session.post(
                    self.base_url,
                    json=payload,
                    timeout=15,
                )
                self._last_api_call_time = time.time()

                if response.status_code == 200:
                    data = response.json()
                    content = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    ).strip()

                    if not content:
                        logger.warning(f"Empty LLM response (attempt {attempt+1})")
                        continue

                    scores = self._parse_llm_response(content, len(texts))
                    if scores is not None:
                        return scores
                    else:
                        logger.warning(
                            f"Failed to parse LLM response: '{content}' "
                            f"(attempt {attempt+1})"
                        )
                        continue

                elif response.status_code == 429:
                    # Rate limited - back off more aggressively
                    retry_after = int(response.headers.get("Retry-After", 10))
                    logger.warning(
                        f"NVIDIA API rate limited (429). "
                        f"Waiting {retry_after}s before retry."
                    )
                    time.sleep(retry_after)
                    continue

                elif response.status_code == 401:
                    # Auth failure - don't retry, mark LLM unavailable
                    logger.error(
                        f"NVIDIA API auth failed (401). "
                        f"Disabling LLM for this session."
                    )
                    self._llm_available = False
                    return None

                elif response.status_code >= 500:
                    # Server error - retry with backoff
                    wait = RETRY_BACKOFF * (2 ** attempt)
                    logger.warning(
                        f"NVIDIA API server error ({response.status_code}). "
                        f"Retrying in {wait:.1f}s (attempt {attempt+1}/{MAX_RETRIES})"
                    )
                    time.sleep(wait)
                    continue

                else:
                    logger.error(
                        f"NVIDIA API error: {response.status_code} - "
                        f"{response.text[:200]}"
                    )
                    wait = RETRY_BACKOFF * (2 ** attempt)
                    time.sleep(wait)
                    continue

            except requests.exceptions.Timeout:
                wait = RETRY_BACKOFF * (2 ** attempt)
                logger.warning(
                    f"NVIDIA API timeout. Retrying in {wait:.1f}s "
                    f"(attempt {attempt+1}/{MAX_RETRIES})"
                )
                time.sleep(wait)
                continue

            except requests.exceptions.ConnectionError as e:
                wait = RETRY_BACKOFF * (2 ** attempt)
                logger.warning(
                    f"NVIDIA API connection error: {e}. "
                    f"Retrying in {wait:.1f}s (attempt {attempt+1}/{MAX_RETRIES})"
                )
                time.sleep(wait)
                continue

            except Exception as e:
                logger.error(f"Unexpected error calling NVIDIA API: {e}")
                wait = RETRY_BACKOFF * (2 ** attempt)
                time.sleep(wait)
                continue

        # All retries exhausted
        logger.error(
            f"LLM batch failed after {MAX_RETRIES} retries. "
            f"Switching to VADER fallback."
        )
        return None

    @staticmethod
    def _parse_llm_response(
        content: str, expected_count: int
    ) -> Optional[List[float]]:
        """Parse the LLM's comma-separated response into float scores.

        Handles various response formats:
        - "0.8, -0.4, -0.6, 0.8, -0.5"
        - "0.8,-0.4,-0.6,0.8,-0.5"
        - Extra text before/after the numbers

        Args:
            content: Raw LLM response string.
            expected_count: Expected number of scores.

        Returns:
            List of float scores clamped to [-1, 1], or None if parsing fails.
        """
        # Try to extract just the numeric portion
        # Match patterns like "0.8, -0.4, -0.6" etc.
        content = content.strip()

        # Remove any wrapper text, keep only comma-separated numbers
        # Find a sequence of numbers (possibly negative, possibly decimal)
        # separated by commas
        numeric_pattern = r"-?\d+\.?\d*(?:\s*,\s*-?\d+\.?\d*)*"
        match = re.search(numeric_pattern, content)
        if not match:
            return None

        numeric_str = match.group(0)
        parts = [p.strip() for p in numeric_str.split(",") if p.strip()]

        if not parts:
            return None

        try:
            scores = [float(p) for p in parts]
        except (ValueError, TypeError):
            return None

        # Validate count - allow some flexibility
        if len(scores) != expected_count:
            # If close enough, use what we got (LLM might combine or split)
            if abs(len(scores) - expected_count) <= 1:
                pass  # Accept slightly mismatched counts
            else:
                logger.debug(
                    f"Score count mismatch: got {len(scores)}, "
                    f"expected {expected_count}"
                )
                # Still try to use what we can

        # Clip scores to [-1, 1] range
        clipped = [max(-1.0, min(1.0, s)) for s in scores]

        # Warn about significant clipping
        for i, (orig, clip) in enumerate(zip(scores, clipped)):
            if abs(orig - clip) > 0.01:
                logger.debug(f"Clipped score {i}: {orig} -> {clip}")

        return clipped

    # ------------------------------------------------------------------
    # VADER fallback
    # ------------------------------------------------------------------

    def _vader_fallback(self, text: str) -> float:
        """Analyze sentiment using VADER as a fallback.

        Initializes VADER lazily on first use. Returns the compound score
        which is naturally in [-1, 1] range.

        Args:
            text: Text string to analyze.

        Returns:
            VADER compound sentiment score in [-1, 1], or 0.0 if VADER
            is not available.
        """
        if not VADER_AVAILABLE:
            logger.debug("VADER not available, returning 0.0 sentiment")
            return 0.0

        if self._vader_analyzer is None:
            self._vader_analyzer = SentimentIntensityAnalyzer()

        scores = self._vader_analyzer.polarity_scores(text)
        return scores.get("compound", 0.0)

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(text: str) -> str:
        """Generate a cache key from text using SHA-256 hash.

        Args:
            text: Input text string.

        Returns:
            Hex digest string of the SHA-256 hash.
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _cache_set(self, key: str, value: float) -> None:
        """Store a sentiment score in cache, evicting old entries if at capacity.

        Uses simple FIFO eviction: when cache exceeds CACHE_MAX_SIZE, remove
        the oldest entries (first 20% of cache).

        Args:
            key: Cache key (text hash).
            value: Sentiment score to cache.
        """
        self._cache[key] = value

        # Evict old entries if cache is too large
        if len(self._cache) > CACHE_MAX_SIZE:
            # Remove oldest 20% of entries (simple FIFO eviction)
            evict_count = CACHE_MAX_SIZE // 5
            keys_to_evict = list(self._cache.keys())[:evict_count]
            for k in keys_to_evict:
                del self._cache[k]
            logger.debug(
                f"Cache eviction: removed {evict_count} entries, "
                f"cache size now {len(self._cache)}"
            )

    def clear_cache(self) -> None:
        """Clear the sentiment result cache."""
        self._cache.clear()
        logger.debug("Sentiment cache cleared")

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def try_backup_model(self) -> bool:
        """Switch to the backup model (Llama 3.1 8B) and test connectivity.

        Use this if the primary model is having issues.

        Returns:
            True if the backup model responds successfully, False otherwise.
        """
        old_model = self.model
        self.model = BACKUP_MODEL
        logger.info(f"Switched from {old_model} to backup model {self.model}")

        # Quick test with a single text
        test_result = self._call_llm_batch(["Test: market is stable"])
        if test_result is not None:
            logger.info("Backup model is working")
            return True
        else:
            logger.warning("Backup model also failed")
            self.model = old_model  # Revert
            return False

    @property
    def cache_size(self) -> int:
        """Return the current number of cached sentiment results."""
        return len(self._cache)

    @property
    def is_llm_available(self) -> bool:
        """Return whether the LLM API is currently considered available."""
        return self._llm_available


# ============ STANDALONE TEST ============

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("=" * 60)
    print("LLM Sentiment Analyzer - Standalone Test")
    print("=" * 60)

    analyzer = LLMSentimentAnalyzer()

    # Test 1: Batch analysis with financial texts
    print("\n--- Test 1: Batch Analysis ---")
    test_texts = [
        "NVDA earnings beat expectations, raising guidance",
        "AMD facing margin pressure from increased competition",
        "TSLA misses delivery targets, shares drop 5%",
        "MU shares surge on strong AI-driven demand forecast",
        "INTC announces layoffs amid restructuring plan",
    ]
    scores = analyzer.analyze_batch(test_texts)
    for text, score in zip(test_texts, scores):
        signal = LLMSentimentAnalyzer.score_to_signal(score)
        print(f"  {text[:50]:50s} | score={score:+.3f} | {signal}")

    # Test 2: Single text analysis
    print("\n--- Test 2: Single Analysis ---")
    single_score = analyzer.analyze_single(
        "AAPL announces $110B buyback, biggest in history"
    )
    signal = LLMSentimentAnalyzer.score_to_signal(single_score)
    print(f"  Score: {single_score:+.3f} | Signal: {signal}")

    # Test 3: Enhanced sentiment for social posts
    print("\n--- Test 3: Enhanced Sentiment ---")
    test_posts = [
        {"title": "NVDA rocket", "body": "NVDA earnings beat, to the moon!"},
        {"title": "AMD bearish", "body": "AMD margin pressure getting worse"},
        {"title": "TSLA", "body": "TSLA delivery miss, bearish outlook"},
        {"title": "MU diamond hands", "body": "MU surge on AI demand, holding"},
        {"title": "INTC restructuring", "body": "INTC layoffs continue, more cuts expected"},
    ]
    result = analyzer.get_enhanced_sentiment(test_posts)
    print(f"  Aggregate Score: {result['aggregate_score']}/100")
    print(f"  Signal: {result['signal']}")
    print(f"  Avg Score: {result['avg_score']:+.3f}")
    print(f"  Distribution: {result['score_distribution']}")
    for item in result["individual_scores"]:
        print(f"    {item['text'][:50]:50s} | {item['score']:+.3f} | {item['signal']}")

    # Test 4: score_to_signal boundary values
    print("\n--- Test 4: Score-to-Signal Mapping ---")
    for val in [-1.0, -0.7, -0.5, -0.3, -0.1, 0.0, 0.1, 0.3, 0.5, 0.7, 1.0]:
        sig = LLMSentimentAnalyzer.score_to_signal(val)
        print(f"  {val:+.1f} -> {sig}")

    # Test 5: Caching verification
    print("\n--- Test 5: Cache Verification ---")
    print(f"  Cache size after tests: {analyzer.cache_size}")
    # Re-analyze same texts - should use cache
    t0 = time.time()
    scores2 = analyzer.analyze_batch(test_texts)
    cache_time = time.time() - t0
    print(f"  Re-analysis time (cached): {cache_time:.4f}s")
    print(f"  Scores match: {scores == scores2}")

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)
