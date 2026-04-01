"""Free-tier API integrations with key rotation.

Multiple free APIs with key rotation to maximize rate limits:
  - NewsAPI.org: 100 req/day per key (rotate multiple free keys)
  - Reddit (PRAW): 100 req/min (free, generous)
  - Google News RSS: unlimited (no key needed)
  - FRED (US economic data): 120 req/min per key

KEY ROTATION: Create multiple free accounts, store keys in .env,
the system rotates through them automatically when rate-limited.

All data is cached (5-30 min TTL) to minimize API calls.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()
_executor = ThreadPoolExecutor(max_workers=4)


# ── Key Rotation Manager ────────────────────────────────────────

class KeyRotator:
    """Rotates through multiple API keys for the same service.

    Store keys in .env as comma-separated:
      NEWSAPI_KEYS=key1,key2,key3
    """

    def __init__(self, env_var: str, separator: str = ",") -> None:
        raw = os.getenv(env_var, "")
        self._keys = [k.strip() for k in raw.split(separator) if k.strip()]
        self._index = 0
        self._exhausted: set[int] = set()  # indices of rate-limited keys
        self._exhausted_until: dict[int, float] = {}  # index -> timestamp

    @property
    def has_keys(self) -> bool:
        return len(self._keys) > 0

    @property
    def key_count(self) -> int:
        return len(self._keys)

    def get_key(self) -> str | None:
        """Get the next available key, skipping exhausted ones."""
        if not self._keys:
            return None

        now = time.time()
        # Un-exhaust keys whose cooldown has passed
        for idx in list(self._exhausted):
            if now > self._exhausted_until.get(idx, 0):
                self._exhausted.discard(idx)

        # Try all keys in round-robin
        for _ in range(len(self._keys)):
            idx = self._index % len(self._keys)
            self._index += 1
            if idx not in self._exhausted:
                return self._keys[idx]

        # All keys exhausted
        return None

    def mark_exhausted(self, key: str, cooldown_sec: float = 3600) -> None:
        """Mark a key as rate-limited. Will be retried after cooldown."""
        try:
            idx = self._keys.index(key)
            self._exhausted.add(idx)
            self._exhausted_until[idx] = time.time() + cooldown_sec
            logger.info("api_key_exhausted", service=f"key_{idx}",
                       cooldown=cooldown_sec, remaining=len(self._keys) - len(self._exhausted))
        except ValueError:
            pass


# ── NewsAPI.org (100 req/day free) ───────────────────────────────

@dataclass
class NewsAPIResult:
    articles: list[dict] = field(default_factory=list)
    total: int = 0
    score: float = 0.0  # aggregate sentiment
    source: str = "newsapi"


class NewsAPICollector:
    """Fetch market news from NewsAPI.org with key rotation.

    Free tier: 100 requests/day per key.
    With 3 keys: 300 requests/day = 1 request every 4.8 minutes.
    """

    def __init__(self) -> None:
        self._rotator = KeyRotator("NEWSAPI_KEYS")
        self._cache: NewsAPIResult | None = None
        self._cache_ts: float = 0
        self._cache_ttl: float = 600  # 10 min cache (conserve quota)

    @property
    def available(self) -> bool:
        return self._rotator.has_keys

    async def fetch(self, query: str = "nifty OR sensex OR indian stock market") -> NewsAPIResult:
        """Fetch latest market news."""
        now = time.time()
        if self._cache and (now - self._cache_ts) < self._cache_ttl:
            return self._cache

        key = self._rotator.get_key()
        if not key:
            return NewsAPIResult()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_executor, self._fetch_sync, key, query)
        if result.total > 0:
            self._cache = result
            self._cache_ts = now
        return result

    def _fetch_sync(self, api_key: str, query: str) -> NewsAPIResult:
        import requests
        try:
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 50,
                    "apiKey": api_key,
                },
                timeout=10,
            )
            if resp.status_code == 429 or resp.status_code == 426:
                self._rotator.mark_exhausted(api_key, 86400)  # 24h cooldown
                return NewsAPIResult()
            if resp.status_code != 200:
                return NewsAPIResult()

            data = resp.json()
            articles = []
            for a in data.get("articles", []):
                articles.append({
                    "title": a.get("title", ""),
                    "source": a.get("source", {}).get("name", ""),
                    "published": a.get("publishedAt", ""),
                    "url": a.get("url", ""),
                })

            # Score with our financial sentiment scorer
            try:
                from trade_plus.market_data.news_sentiment import FinancialSentimentScorer
                scorer = FinancialSentimentScorer()
                scores = [scorer.score(a["title"]) for a in articles if a["title"]]
                avg_score = sum(scores) / len(scores) if scores else 0
            except Exception:
                avg_score = 0

            result = NewsAPIResult(
                articles=articles[:20],
                total=len(articles),
                score=round(avg_score, 4),
            )
            logger.info("newsapi_fetched", articles=len(articles), score=avg_score,
                       keys_remaining=self._rotator.key_count - len(self._rotator._exhausted))
            return result

        except Exception as e:
            logger.warning("newsapi_error", error=str(e))
            return NewsAPIResult()


# ── Reddit Sentiment (r/IndianStreetBets) ────────────────────────

@dataclass
class RedditSentiment:
    score: float = 0.0           # -1 to +1
    bullish_posts: int = 0
    bearish_posts: int = 0
    total_posts: int = 0
    hot_topics: list[str] = field(default_factory=list)
    avg_upvotes: float = 0.0
    source: str = "reddit"


class RedditCollector:
    """Scrape r/IndianStreetBets and r/IndianStockMarket for sentiment.

    Free: 100 requests/min with Reddit API (very generous).
    Useful as CONTRARIAN indicator — extreme bullishness = top signal.
    """

    def __init__(self) -> None:
        self._reddit = None
        self._cache: RedditSentiment | None = None
        self._cache_ts: float = 0
        self._cache_ttl: float = 900  # 15 min cache

    def _init_reddit(self):
        """Lazy init Reddit client."""
        if self._reddit is not None:
            return True

        client_id = os.getenv("REDDIT_CLIENT_ID", "")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")

        if not client_id or not client_secret:
            return False

        try:
            import praw
            self._reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent="trade-plus-sentiment/1.0",
            )
            return True
        except Exception as e:
            logger.warning("reddit_init_failed", error=str(e))
            return False

    @property
    def available(self) -> bool:
        return bool(os.getenv("REDDIT_CLIENT_ID"))

    async def fetch(self) -> RedditSentiment:
        """Fetch and score posts from Indian finance subreddits."""
        now = time.time()
        if self._cache and (now - self._cache_ts) < self._cache_ttl:
            return self._cache

        if not self._init_reddit():
            return RedditSentiment()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_executor, self._fetch_sync)
        if result.total_posts > 0:
            self._cache = result
            self._cache_ts = now
        return result

    def _fetch_sync(self) -> RedditSentiment:
        try:
            from trade_plus.market_data.news_sentiment import FinancialSentimentScorer
            scorer = FinancialSentimentScorer()

            subreddits = ["IndianStreetBets", "IndianStockMarket"]
            all_posts = []

            for sub_name in subreddits:
                try:
                    sub = self._reddit.subreddit(sub_name)
                    for post in sub.hot(limit=25):
                        title = post.title
                        label, score = scorer.classify(title)
                        all_posts.append({
                            "title": title,
                            "score": score,
                            "label": label,
                            "upvotes": post.score,
                            "comments": post.num_comments,
                            "sub": sub_name,
                        })
                except Exception as e:
                    logger.debug("reddit_sub_error", sub=sub_name, error=str(e))

            if not all_posts:
                return RedditSentiment()

            scores = [p["score"] for p in all_posts]
            avg_score = sum(scores) / len(scores)
            bullish = sum(1 for p in all_posts if p["label"] == "bullish")
            bearish = sum(1 for p in all_posts if p["label"] == "bearish")
            avg_upvotes = sum(p["upvotes"] for p in all_posts) / len(all_posts)

            # Top trending topics
            hot = sorted(all_posts, key=lambda p: p["upvotes"], reverse=True)[:5]
            hot_topics = [p["title"][:80] for p in hot]

            result = RedditSentiment(
                score=round(avg_score, 4),
                bullish_posts=bullish,
                bearish_posts=bearish,
                total_posts=len(all_posts),
                hot_topics=hot_topics,
                avg_upvotes=round(avg_upvotes, 0),
            )

            logger.info("reddit_sentiment", score=avg_score,
                       bullish=bullish, bearish=bearish,
                       total=len(all_posts))
            return result

        except Exception as e:
            logger.warning("reddit_fetch_error", error=str(e))
            return RedditSentiment()


# ── Combined free data aggregator ────────────────────────────────

class FreeDataAggregator:
    """Orchestrates all free data sources with caching and fallbacks."""

    def __init__(self) -> None:
        self.newsapi = NewsAPICollector()
        self.reddit = RedditCollector()
        self._sources_status: dict[str, bool] = {}

    async def collect_all(self) -> dict:
        """Collect from all available free sources.

        Returns combined dict with data from each source.
        Skips sources that aren't configured.
        """
        result = {"sources": []}

        # NewsAPI (if keys configured)
        if self.newsapi.available:
            try:
                news = await self.newsapi.fetch()
                if news.total > 0:
                    result["newsapi"] = {
                        "score": news.score,
                        "articles": news.total,
                        "top_articles": news.articles[:5],
                    }
                    result["sources"].append("newsapi")
            except Exception as e:
                logger.debug("newsapi_collect_error", error=str(e))

        # Reddit (if credentials configured)
        if self.reddit.available:
            try:
                reddit = await self.reddit.fetch()
                if reddit.total_posts > 0:
                    result["reddit"] = {
                        "score": reddit.score,
                        "bullish": reddit.bullish_posts,
                        "bearish": reddit.bearish_posts,
                        "total": reddit.total_posts,
                        "hot_topics": reddit.hot_topics,
                        "avg_upvotes": reddit.avg_upvotes,
                    }
                    result["sources"].append("reddit")
            except Exception as e:
                logger.debug("reddit_collect_error", error=str(e))

        # Compute blended sentiment from all available sources
        scores = []
        if "newsapi" in result:
            scores.append(result["newsapi"]["score"])
        if "reddit" in result:
            scores.append(result["reddit"]["score"])

        result["blended_score"] = round(sum(scores) / len(scores), 4) if scores else 0
        result["source_count"] = len(result["sources"])

        return result
