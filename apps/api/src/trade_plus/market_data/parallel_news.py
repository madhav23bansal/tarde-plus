"""Parallel AI — real-time news search with deduplication.

Uses Parallel's search API to fetch latest news articles about
Indian market instruments, then scores sentiment with VADER.
Deduplication is handled server-side by Parallel.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

import httpx
import structlog

logger = structlog.get_logger()

PARALLEL_BASE_URL = "https://api.parallel.ai"

# Sector-specific search objectives
SECTOR_OBJECTIVES = {
    "index": "Latest news about Nifty 50, Indian stock market, Sensex, and NSE market movements today",
    "gold": "Latest gold price news, COMEX gold forecast, gold ETF India, and precious metals market today",
    "silver": "Latest silver price news, silver market forecast, precious metals, and industrial metals today",
    "banking": "Latest Indian banking sector news, Bank Nifty, RBI policy, credit growth, NPA data today",
}

SECTOR_QUERIES = {
    "index": ["Nifty 50 market today", "Indian stock market news", "FII DII activity NSE"],
    "gold": ["gold price today", "gold market forecast", "COMEX gold news"],
    "silver": ["silver price today", "silver market news", "precious metals forecast"],
    "banking": ["Bank Nifty today", "Indian banking news", "RBI monetary policy"],
}


@dataclass
class NewsArticle:
    title: str = ""
    url: str = ""
    excerpt: str = ""
    published: str = ""
    sentiment: float = 0.0  # -1 to +1


@dataclass
class NewsSentiment:
    score: float = 0.0          # -1 to +1 aggregate
    article_count: int = 0
    articles: list[NewsArticle] = field(default_factory=list)
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    source: str = "parallel"


class ParallelNewsClient:
    """Fetches real-time news via Parallel AI search API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=PARALLEL_BASE_URL,
                headers={
                    "x-api-key": self._api_key,
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(30.0),
            )
        return self._client

    async def search_news(self, sector: str, max_results: int = 10) -> NewsSentiment:
        """Search for latest news about a sector and score sentiment."""
        client = await self._ensure_client()

        objective = SECTOR_OBJECTIVES.get(sector, SECTOR_OBJECTIVES["index"])
        queries = SECTOR_QUERIES.get(sector, SECTOR_QUERIES["index"])

        try:
            resp = await client.post("/alpha/search", json={
                "objective": objective,
                "search_queries": queries,
                "max_results": max_results,
            })
            resp.raise_for_status()
            data = resp.json()

            articles = []
            for result in data.get("results", []):
                title = result.get("title", "")
                excerpts = result.get("excerpts", [])
                excerpt = " ".join(excerpts)[:300] if excerpts else ""
                url = result.get("url", "")
                published = result.get("publish_date", "")

                articles.append(NewsArticle(
                    title=title,
                    url=url,
                    excerpt=excerpt,
                    published=published,
                ))

            # Score sentiment with VADER
            scored = self._score_articles(articles)

            return scored

        except httpx.HTTPStatusError as e:
            logger.warning("parallel_api_error", status=e.response.status_code,
                          body=e.response.text[:200])
            return NewsSentiment(source="parallel_error")
        except Exception as e:
            logger.warning("parallel_error", error=str(e))
            return NewsSentiment(source="parallel_error")

    def _score_articles(self, articles: list[NewsArticle]) -> NewsSentiment:
        """Score articles with VADER sentiment."""
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            analyzer = SentimentIntensityAnalyzer()
        except ImportError:
            return NewsSentiment(articles=articles, article_count=len(articles), source="parallel_no_vader")

        scores = []
        pos = neg = neu = 0

        for article in articles:
            text = f"{article.title}. {article.excerpt}"
            result = analyzer.polarity_scores(text)
            article.sentiment = result["compound"]
            scores.append(result["compound"])

            if result["compound"] > 0.05:
                pos += 1
            elif result["compound"] < -0.05:
                neg += 1
            else:
                neu += 1

        avg_score = sum(scores) / len(scores) if scores else 0.0

        return NewsSentiment(
            score=round(avg_score, 4),
            article_count=len(articles),
            articles=articles,
            positive_count=pos,
            negative_count=neg,
            neutral_count=neu,
            source="parallel",
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
