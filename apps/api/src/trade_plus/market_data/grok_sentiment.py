"""xAI Grok — X/Twitter sentiment analysis and trending topics.

Uses Grok's chat completions with x_search tool to:
1. Search X for real-time posts about Indian market instruments
2. Score sentiment of posts via grok-3-mini (cheap + fast)
3. Extract trending topics and influencer activity

Cost: ~$0.30/1M tokens with grok-3-mini
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import httpx
import structlog

logger = structlog.get_logger()

GROK_BASE_URL = "https://api.x.ai/v1"
SENTIMENT_MODEL = "grok-3-mini"  # cheap for batch sentiment

# Sector-specific search queries for X
SECTOR_QUERIES = {
    "index": ["#Nifty50 OR #Sensex OR NIFTYBEES", "#indianstockmarket OR #NSE trading"],
    "gold": ["#Gold OR #XAUUSD price", "gold investment India OR #GOLDBEES"],
    "silver": ["#Silver OR #XAGUSD price", "silver market India OR #SILVERBEES"],
    "banking": ["#BankNifty OR #banking stocks India", "#RBI OR banking sector #NSE"],
}


@dataclass
class SocialSentiment:
    score: float = 0.0          # -1 to +1
    positive_pct: float = 0.0
    negative_pct: float = 0.0
    neutral_pct: float = 0.0
    post_count: int = 0
    trending_topics: list[str] = field(default_factory=list)
    key_posts: list[str] = field(default_factory=list)
    source: str = "grok_x"


class GrokSentimentClient:
    """Collects X/Twitter sentiment via xAI Grok API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=GROK_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(30.0),
            )
        return self._client

    async def get_sentiment(self, sector: str, instrument: str) -> SocialSentiment:
        """Get X/Twitter sentiment for a sector/instrument.

        Uses Grok to search X and analyze sentiment in one call.
        """
        client = await self._ensure_client()

        queries = SECTOR_QUERIES.get(sector, SECTOR_QUERIES["index"])
        search_term = queries[0]

        prompt = f"""Search X (Twitter) for recent posts about "{search_term}" from the last 24 hours.

Analyze the sentiment of the posts and return a JSON object with:
{{
  "score": <float -1.0 to +1.0, overall sentiment>,
  "positive_pct": <float 0-100>,
  "negative_pct": <float 0-100>,
  "neutral_pct": <float 0-100>,
  "post_count": <int, approximate number of relevant posts found>,
  "trending_topics": [<top 3 related trending topics>],
  "key_posts": [<3 most impactful post summaries, max 100 chars each>]
}}

Focus on sentiment about {instrument} and the Indian stock market.
Return ONLY the JSON, no other text."""

        try:
            # Use Grok's chat completions — the model has built-in X knowledge
            # The old search_parameters API is deprecated (410 Gone)
            resp = await client.post("/chat/completions", json={
                "model": SENTIMENT_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a financial sentiment analyst with real-time knowledge of X (Twitter) posts about financial markets. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 500,
            })
            resp.raise_for_status()
            data = resp.json()

            content = data["choices"][0]["message"]["content"]

            # Parse JSON from response (handle markdown code blocks)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result = json.loads(content.strip())

            return SocialSentiment(
                score=float(result.get("score", 0)),
                positive_pct=float(result.get("positive_pct", 0)),
                negative_pct=float(result.get("negative_pct", 0)),
                neutral_pct=float(result.get("neutral_pct", 0)),
                post_count=int(result.get("post_count", 0)),
                trending_topics=result.get("trending_topics", [])[:5],
                key_posts=result.get("key_posts", [])[:5],
                source="grok_x",
            )

        except httpx.HTTPStatusError as e:
            logger.warning("grok_api_error", status=e.response.status_code,
                          body=e.response.text[:200])
            return SocialSentiment(source="grok_x_error")
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning("grok_parse_error", error=str(e))
            return SocialSentiment(source="grok_x_parse_error")
        except Exception as e:
            logger.warning("grok_error", error=str(e))
            return SocialSentiment(source="grok_x_error")

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
