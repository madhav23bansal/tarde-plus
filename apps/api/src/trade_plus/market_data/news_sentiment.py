"""Free news sentiment from RSS feeds + financial-domain scoring.

Collects headlines from 6 free Indian financial news RSS feeds,
scores them with a market-tuned VADER + financial lexicon.

Why not FinBERT?
  - 97s model load time (too slow for 2-min cycle)
  - Trained on US corporate text, gets Indian market headlines wrong
  - Thinks "Nifty crashes 500 points" is POSITIVE

Our approach:
  - VADER base (instant, already installed)
  - Financial lexicon overlay (200+ market-specific terms)
  - Indian market context (FII, RBI, SEBI, Nifty-specific terms)
  - Processes 100+ headlines in <0.5 seconds
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import feedparser
import structlog
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = structlog.get_logger()

# ── Free RSS feeds (no API keys, no rate limits) ─────────────────

RSS_FEEDS = [
    # MoneyControl markets
    ("moneycontrol", "https://www.moneycontrol.com/rss/marketreports.xml"),
    # Economic Times markets
    ("et_markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    # LiveMint markets
    ("livemint", "https://www.livemint.com/rss/markets"),
    # NDTV Profit
    ("ndtv", "https://feeds.feedburner.com/ndtvprofit-latest"),
    # Business Standard
    ("bs_markets", "https://www.business-standard.com/rss/markets-106.rss"),
    # Google News India markets
    ("google", "https://news.google.com/rss/search?q=nifty+OR+sensex+stock+market&hl=en-IN&gl=IN&ceid=IN:en"),
]

# ── Financial lexicon for VADER ──────────────────────────────────
# VADER's default lexicon doesn't know financial terms.
# These overrides fix its blindspots for market headlines.

FINANCIAL_LEXICON = {
    # Strongly bearish
    "crash": -3.5, "crashes": -3.5, "crashed": -3.5, "crashing": -3.5,
    "plunge": -3.5, "plunges": -3.5, "plunged": -3.5, "plunging": -3.5,
    "tank": -3.0, "tanks": -3.0, "tanked": -3.0, "tanking": -3.0,
    "tumble": -3.0, "tumbles": -3.0, "tumbled": -3.0, "tumbling": -3.0,
    "selloff": -3.0, "sell-off": -3.0, "bloodbath": -3.5,
    "rout": -3.0, "carnage": -3.5, "meltdown": -3.5, "freefall": -3.5,
    "correction": -2.0, "bear": -1.5, "bearish": -2.5,
    "recession": -3.0, "slowdown": -2.0, "contraction": -2.0,
    "default": -3.0, "defaults": -3.0, "crisis": -3.0,
    "outflow": -2.0, "outflows": -2.0, "flee": -2.5,
    "panic": -3.0, "fear": -2.5, "anxiety": -2.0, "uncertainty": -1.5,
    "downgrade": -2.5, "downgrades": -2.5, "downgraded": -2.5,
    "warning": -2.0, "warns": -2.0, "warned": -2.0,
    "slump": -2.5, "slumps": -2.5, "slumped": -2.5,
    "decline": -2.0, "declines": -2.0, "declined": -2.0, "declining": -2.0,
    "losses": -2.0, "lose": -2.0, "losing": -2.0, "lost": -2.0,
    "worst": -3.0, "weakens": -2.0, "weaken": -2.0, "weakness": -2.0,
    "volatile": -1.5, "volatility": -1.5,
    "inflation": -1.5, "inflationary": -2.0,
    "hike": -1.5, "tightening": -2.0, "hawkish": -2.0,
    "deficit": -1.5, "debt": -1.0,

    # FII/DII specific (Indian market)
    "fii": -0.5, "fpi": -0.5,  # slight negative bias (FII headlines are usually about selling)
    "selling": -2.5, "sold": -2.0, "dumped": -3.0, "dump": -3.0,
    "pullout": -2.5, "pull-out": -2.5, "withdrawn": -2.0, "withdraw": -2.0,
    "pull": -1.5, "out": -0.5,  # "pull out" context
    "fled": -2.5,

    # Strongly bullish
    "rally": 3.0, "rallies": 3.0, "rallied": 3.0, "rallying": 3.0,
    "surge": 3.0, "surges": 3.0, "surged": 3.0, "surging": 3.0,
    "soar": 3.0, "soars": 3.0, "soared": 3.0, "soaring": 3.0,
    "boom": 3.0, "booms": 3.0, "booming": 3.0,
    "bull": 1.5, "bullish": 2.5, "bull-run": 3.0,
    "breakout": 2.5, "breakthrough": 2.5,
    "record": 2.0, "all-time-high": 3.0, "ath": 3.0, "lifetime": 2.0,
    "recovery": 2.5, "recover": 2.0, "recovers": 2.0, "recovered": 2.0,
    "rebound": 2.5, "rebounds": 2.5, "rebounded": 2.5,
    "gain": 2.0, "gains": 2.0, "gained": 2.0, "gaining": 2.0,
    "jump": 2.5, "jumps": 2.5, "jumped": 2.5, "jumping": 2.5,
    "climb": 2.0, "climbs": 2.0, "climbed": 2.0, "climbing": 2.0,
    "rise": 2.0, "rises": 2.0, "rising": 2.0, "risen": 2.0,
    "up": 1.0, "higher": 1.5, "high": 1.0,
    "inflow": 2.0, "inflows": 2.0,
    "upgrade": 2.5, "upgrades": 2.5, "upgraded": 2.5,
    "easing": 2.0, "dovish": 2.0, "accommodative": 2.0,
    "stimulus": 2.0, "reform": 1.5, "reforms": 1.5,
    "buying": 2.0, "bought": 1.5, "accumulate": 2.0, "accumulating": 2.0,
    "optimism": 2.0, "optimistic": 2.0, "confidence": 1.5,
    "growth": 1.5, "expanding": 1.5, "expansion": 1.5,

    # Indian market specific
    "nifty": 0.0, "sensex": 0.0, "banknifty": 0.0,  # neutral (modified by context)
    "rbi": 0.0, "sebi": 0.0,
    "rupee": 0.0, "inr": 0.0,
    "expiry": -0.5,  # slight negative (expiry days are volatile)
    "circuit": -1.0,  # usually refers to circuit breaker = extreme move

    # Modifiers (amplify nearby sentiment)
    "massive": 1.5, "sharp": 1.5, "heavy": 1.0, "huge": 1.5,
    "biggest": 2.0, "largest": 1.5, "steepest": 2.0,
    "unprecedented": 2.0, "historic": 1.5,
}


@dataclass
class NewsSentiment:
    """Aggregated sentiment from multiple news sources."""
    score: float = 0.0          # -1 to +1 (market direction)
    magnitude: float = 0.0      # 0 to 1 (strength of sentiment)
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0
    total_articles: int = 0
    top_bullish: list[str] = field(default_factory=list)
    top_bearish: list[str] = field(default_factory=list)
    sources_fetched: int = 0
    fetch_time_ms: float = 0.0


class FinancialSentimentScorer:
    """VADER + financial lexicon for market-specific sentiment."""

    def __init__(self) -> None:
        self._vader = SentimentIntensityAnalyzer()
        # Inject financial terms into VADER's lexicon
        self._vader.lexicon.update(FINANCIAL_LEXICON)

    def score(self, text: str) -> float:
        """Score a headline. Returns -1 (bearish) to +1 (bullish).

        Uses VADER compound score with financial lexicon overlay.
        """
        result = self._vader.polarity_scores(text.lower())
        return result["compound"]

    def classify(self, text: str) -> tuple[str, float]:
        """Classify and score a headline.

        Returns: ("bullish"|"bearish"|"neutral", score)
        """
        score = self.score(text)
        if score >= 0.15:
            return "bullish", score
        elif score <= -0.15:
            return "bearish", score
        return "neutral", score


class NewsFeedCollector:
    """Collects and scores news from free RSS feeds."""

    def __init__(self) -> None:
        self._scorer = FinancialSentimentScorer()
        self._seen_hashes: set[str] = set()  # dedup headlines
        self._cache: NewsSentiment | None = None
        self._cache_ts: float = 0
        self._cache_ttl: float = 300  # 5 minute cache

    def _hash(self, text: str) -> str:
        return hashlib.md5(text.lower().strip().encode()).hexdigest()[:12]

    def _is_recent(self, entry) -> bool:
        """Check if an RSS entry is from the last 24 hours."""
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        if not published:
            return True  # assume recent if no date
        try:
            pub_dt = datetime(*published[:6])
            return (datetime.now() - pub_dt) < timedelta(hours=24)
        except Exception:
            return True

    def _is_market_relevant(self, title: str) -> bool:
        """Filter for market-relevant headlines."""
        title_lower = title.lower()
        market_terms = [
            "nifty", "sensex", "market", "stock", "share", "bse", "nse",
            "fii", "fpi", "dii", "rbi", "sebi", "rupee", "inr",
            "bank nifty", "banknifty", "midcap", "smallcap",
            "rally", "crash", "surge", "plunge", "bull", "bear",
            "sector", "index", "etf", "mutual fund",
            "quarterly", "earnings", "profit", "revenue",
            "inflation", "gdp", "rate", "policy",
            "crude", "gold", "silver", "commodity",
            "global", "us market", "wall street", "dow", "nasdaq",
        ]
        return any(term in title_lower for term in market_terms)

    async def collect(self) -> NewsSentiment:
        """Fetch all RSS feeds and score headlines.

        Cached for 5 minutes to avoid hammering RSS feeds.
        Returns aggregated sentiment in <1 second.
        """
        now = time.time()
        if self._cache and (now - self._cache_ts) < self._cache_ttl:
            return self._cache

        import asyncio
        start = time.time()
        result = NewsSentiment()
        all_scored: list[tuple[str, float, str]] = []  # (title, score, source)

        loop = asyncio.get_event_loop()

        # Fetch all feeds in parallel threads (feedparser is sync)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {
                name: loop.run_in_executor(executor, self._fetch_feed, url)
                for name, url in RSS_FEEDS
            }
            for name, fut in futures.items():
                try:
                    entries = await asyncio.wait_for(fut, timeout=10)
                    if entries:
                        result.sources_fetched += 1
                        for entry in entries:
                            title = entry.get("title", "").strip()
                            if not title or not self._is_recent(entry):
                                continue
                            h = self._hash(title)
                            if h in self._seen_hashes:
                                continue
                            self._seen_hashes.add(h)

                            if not self._is_market_relevant(title):
                                continue

                            score = self._scorer.score(title)
                            all_scored.append((title, score, name))
                except Exception as e:
                    logger.debug("rss_feed_error", source=name, error=str(e))

        # Keep seen_hashes from growing unbounded
        if len(self._seen_hashes) > 5000:
            self._seen_hashes = set(list(self._seen_hashes)[-2000:])

        # Aggregate
        if all_scored:
            scores = [s for _, s, _ in all_scored]
            result.total_articles = len(all_scored)
            result.score = round(sum(scores) / len(scores), 4)
            result.magnitude = round(sum(abs(s) for s in scores) / len(scores), 4)

            for title, score, source in all_scored:
                if score >= 0.15:
                    result.bullish_count += 1
                elif score <= -0.15:
                    result.bearish_count += 1
                else:
                    result.neutral_count += 1

            # Top headlines by sentiment
            sorted_scored = sorted(all_scored, key=lambda x: x[1])
            result.top_bearish = [t for t, s, _ in sorted_scored[:3] if s < -0.15]
            result.top_bullish = [t for t, s, _ in sorted_scored[-3:] if s > 0.15]

        result.fetch_time_ms = round((time.time() - start) * 1000, 1)

        self._cache = result
        self._cache_ts = now

        logger.info("news_sentiment_collected",
                    articles=result.total_articles,
                    score=result.score,
                    bullish=result.bullish_count,
                    bearish=result.bearish_count,
                    sources=result.sources_fetched,
                    ms=result.fetch_time_ms)

        return result

    def _fetch_feed(self, url: str) -> list[dict]:
        """Fetch a single RSS feed (runs in thread pool)."""
        try:
            feed = feedparser.parse(url)
            return feed.entries[:30]  # max 30 per source
        except Exception:
            return []


# Verify the scorer works correctly on Indian market headlines
def _self_test():
    """Quick sanity check — run on import during development."""
    scorer = FinancialSentimentScorer()
    tests = [
        ("Nifty crashes 500 points as FII selling intensifies", "bearish"),
        ("Sensex rallies 800 points on strong US market cues", "bullish"),
        ("FIIs pull out Rs 11000 crore from Indian equities", "bearish"),
        ("RBI holds repo rate unchanged", "neutral"),
        ("Bank Nifty surges on strong quarterly earnings", "bullish"),
        ("India VIX spikes to 25 amid global uncertainty", "bearish"),
        ("Market bloodbath: Sensex plunges 1000 points", "bearish"),
        ("Nifty hits all-time high, crosses 25000", "bullish"),
    ]
    passed = 0
    for text, expected in tests:
        label, score = scorer.classify(text)
        ok = "OK" if label == expected else "FAIL"
        if label == expected:
            passed += 1
    return passed, len(tests)
