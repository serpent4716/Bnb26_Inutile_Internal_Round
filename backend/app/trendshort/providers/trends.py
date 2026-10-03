"""Pluggable trend sources behind one interface. Each fails gracefully (returns [] and logs)."""
from __future__ import annotations

import asyncio
import logging
import math
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import httpx

from ..config import settings
from ..logging_setup import log
from ..ratelimit import ProviderUnavailable, limiter, raise_for_status, with_backoff
from ..schemas import TrendItem
from . import mock_data

logger = logging.getLogger("t2s.trends")

# YouTube category ids (videoCategoryId) for the filter UI
YT_CATEGORIES = {"general": None, "tech": "28", "science": "28", "lifestyle": "26", "food": "26",
                 "nature": "15", "entertainment": "24", "gaming": "20", "music": "10", "sports": "17"}


def _iso8601_seconds(d: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 10**6
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def _normalize(values: list[float]) -> list[float]:
    """Log-scale to 0..100 within a source so sources are roughly comparable."""
    if not values:
        return []
    logs = [math.log10(max(v, 1)) for v in values]
    lo, hi = min(logs), max(logs)
    if hi - lo < 1e-9:
        return [70.0 for _ in values]
    return [round(30 + 70 * (x - lo) / (hi - lo), 1) for x in logs]


class TrendProvider(ABC):
    name: str
    official: bool = True

    @abstractmethod
    def configured(self) -> tuple[bool, str]: ...

    @abstractmethod
    async def fetch(self, region: str, category: str | None) -> list[TrendItem]: ...


class YouTubeTrends(TrendProvider):
    name = "youtube"

    def configured(self) -> tuple[bool, str]:
        return (bool(settings.youtube_api_key), "missing key YOUTUBE_API_KEY")

    async def fetch(self, region: str, category: str | None) -> list[TrendItem]:
        params = {"part": "snippet,contentDetails,statistics", "chart": "mostPopular", "maxResults": 50,
                  "regionCode": region, "key": settings.youtube_api_key}
        cat_id = YT_CATEGORIES.get(category or "general")
        if cat_id:
            params["videoCategoryId"] = cat_id

        async def call():
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get("https://www.googleapis.com/youtube/v3/videos", params=params)
            raise_for_status(self.name, r.status_code, dict(r.headers), r.text)
            return r.json()

        data = await with_backoff(lambda: limiter("youtube").run(call))
        now = datetime.now(timezone.utc)
        rows = []
        for v in data.get("items", []):
            secs = _iso8601_seconds(v["contentDetails"].get("duration", ""))
            pub = datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))
            hours = max((now - pub).total_seconds() / 3600, 1)
            views = int(v.get("statistics", {}).get("viewCount", 0))
            rows.append((secs, views / hours, v))
        shorts = [r for r in rows if r[0] <= 60]
        rows = shorts if len(shorts) >= 5 else rows   # prefer Shorts-length; fall back if too few
        scores = _normalize([r[1] for r in rows])
        return [TrendItem(id=f"yt-{v['id']}", title=v["snippet"]["title"][:140], source="youtube", region=region,
                          category=category or "general", momentum_score=s,
                          sample_urls=[f"https://www.youtube.com/watch?v={v['id']}"])
                for (_, _, v), s in zip(rows[:20], scores[:20])]


GT_NS = {"ht": "https://trends.google.com/trending/rss"}


def _traffic(text: str) -> float:
    """'2,000+' / '20K+' / '1M+' -> number."""
    t = (text or "").replace(",", "").replace("+", "").strip().upper()
    mult = 1_000 if t.endswith("K") else 1_000_000 if t.endswith("M") else 1
    try:
        return float(t.rstrip("KM")) * mult
    except ValueError:
        return 0.0


def parse_google_trends_rss(xml_text: str, region: str, category: str | None) -> list[TrendItem]:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_text)
    rows = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        traffic = _traffic(item.findtext("ht:approx_traffic", default="", namespaces=GT_NS))
        news = [u.text for u in item.findall("ht:news_item/ht:news_item_url", GT_NS) if u.text]
        rows.append((title, traffic, news))
    scores = _normalize([r[1] for r in rows])
    return [TrendItem(id=f"gt-{region}-{re.sub(r'[^a-z0-9]+', '-', t.lower()).strip('-')[:40]}", title=t,
                      source="google_trends", region=region, category=category or "general", momentum_score=sc,
                      sample_urls=(news[:2] or [f"https://trends.google.com/trending?geo={region}"]))
            for (t, _, news), sc in zip(rows[:20], scores[:20])]


class GoogleTrends(TrendProvider):
    """Google Trends "Trending now" public RSS feed (no key). Replaces pytrends, whose
    trending_searches endpoint now returns 404. Unofficial use, best-effort."""
    name = "google_trends"
    official = False

    def configured(self) -> tuple[bool, str]:
        return True, ""

    async def fetch(self, region: str, category: str | None) -> list[TrendItem]:
        async def call():
            async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                         headers={"User-Agent": "Mozilla/5.0 (trend-to-short)"}) as c:
                r = await c.get("https://trends.google.com/trending/rss", params={"geo": region})
            if r.status_code in (401, 403):
                raise ProviderUnavailable(f"google_trends: blocked ({r.status_code})")
            raise_for_status(self.name, r.status_code, dict(r.headers), r.text[:200])
            return r.text
        return parse_google_trends_rss(await limiter("google_trends").run(call), region, category)


class RedditTrends(TrendProvider):
    """Uses Reddit's OAuth API (app-only) when REDDIT_CLIENT_ID/SECRET are set; otherwise tries the
    public .json listings, which Reddit now often blocks with 403. Best-effort either way."""
    name = "reddit"
    official = False
    _token: tuple[str, float] | None = None

    def configured(self) -> tuple[bool, str]:
        return True, ""

    async def _get_token(self, c: httpx.AsyncClient) -> str | None:
        if not (settings.reddit_client_id and settings.reddit_client_secret):
            return None
        now = datetime.now(timezone.utc).timestamp()
        if RedditTrends._token and RedditTrends._token[1] > now + 60:
            return RedditTrends._token[0]
        r = await c.post("https://www.reddit.com/api/v1/access_token",
                         auth=(settings.reddit_client_id, settings.reddit_client_secret),
                         data={"grant_type": "client_credentials"})
        if r.status_code != 200:
            raise ProviderUnavailable(f"reddit: OAuth token failed ({r.status_code}); check REDDIT_CLIENT_ID/SECRET")
        d = r.json()
        RedditTrends._token = (d["access_token"], now + float(d.get("expires_in", 3600)))
        return d["access_token"]

    async def fetch(self, region: str, category: str | None) -> list[TrendItem]:
        items: list[tuple[float, dict]] = []
        now = datetime.now(timezone.utc).timestamp()
        errors = []
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": settings.reddit_user_agent},
                                     follow_redirects=True) as c:
            token = await self._get_token(c)
            base = "https://oauth.reddit.com" if token else "https://www.reddit.com"
            headers = {"Authorization": f"bearer {token}"} if token else {}
            for sub in [s.strip() for s in settings.reddit_subreddits.split(",") if s.strip()]:
                async def call(sub=sub):
                    path = f"/r/{sub}/hot" if token else f"/r/{sub}/hot.json"
                    r = await c.get(base + path, params={"limit": 15, "raw_json": 1}, headers=headers)
                    if r.status_code in (401, 403, 429) and not token:
                        raise ProviderUnavailable(
                            f"reddit blocked anonymous access ({r.status_code}); set REDDIT_CLIENT_ID/SECRET")
                    raise_for_status(self.name, r.status_code, dict(r.headers), "")
                    return r.json()
                try:
                    data = await limiter("reddit").run(call)
                except Exception as e:  # noqa: BLE001 - one subreddit failing is fine
                    errors.append(str(e)[:120])
                    continue
                for ch in data.get("data", {}).get("children", []):
                    p = ch["data"]
                    if p.get("stickied") or p.get("over_18"):
                        continue
                    age_h = max((now - p.get("created_utc", now)) / 3600, 1)
                    items.append((p.get("score", 0) / age_h, p))
        if not items and errors:
            raise ProviderUnavailable(errors[0])
        items.sort(key=lambda x: -x[0])
        scores = _normalize([x[0] for x in items[:20]])
        return [TrendItem(id=f"rd-{p['id']}", title=p["title"][:140], source="reddit", region=region,
                          category=category or "general", momentum_score=s,
                          sample_urls=[f"https://www.reddit.com{p['permalink']}"])
                for (_, p), s in zip(items[:20], scores)]


class MockTrends(TrendProvider):
    name = "mock"

    def configured(self) -> tuple[bool, str]:
        return True, ""

    async def fetch(self, region: str, category: str | None) -> list[TrendItem]:
        out = []
        for t in mock_data.seed():
            if region and region != "ALL" and t["region"] != region:
                continue
            if category and category != "general" and t["category"] != category:
                continue
            out.append(TrendItem(**{k: t[k] for k in TrendItem.model_fields}))
        return out


def providers() -> list[TrendProvider]:
    if settings.mock_mode:
        return [MockTrends()]
    enabled = {s.strip().lower() for s in settings.trend_sources.split(",") if s.strip()}
    return [p for p in all_providers() if p.name in enabled]


def all_providers() -> list[TrendProvider]:
    return [YouTubeTrends(), GoogleTrends(), RedditTrends()]


REGION_AWARE = {"youtube", "google_trends"}


async def fetch_all(region: str, category: str | None) -> tuple[list[TrendItem], dict[str, str]]:
    """Returns items + a per-provider status map. Never raises.
    region=ALL fans out to TREND_ALL_REGIONS for region-aware sources (YouTube/Google need a real code)."""
    status: dict[str, str] = {}
    results: list[TrendItem] = []

    async def one(p: TrendProvider):
        ok, why = p.configured()
        if not ok:
            status[p.name] = f"skipped: {why}"
            return []
        try:
            if region.upper() == "ALL" and p.name in REGION_AWARE:
                regions = [r.strip().upper() for r in settings.trend_all_regions.split(",") if r.strip()]
                items = []
                for r in regions:
                    try:
                        items += await p.fetch(r, category)
                    except Exception as e:  # noqa: BLE001 - one region failing is fine
                        log(logger, "region fetch failed", logging.WARNING, provider=p.name, region=r, error=str(e)[:150])
                if not items:
                    raise ProviderUnavailable(f"no results for regions {regions}")
            else:
                items = await p.fetch(region, category)   # mock/reddit handle ALL themselves
            status[p.name] = f"ok ({len(items)})"
            return items
        except ProviderUnavailable as e:
            status[p.name] = f"unavailable: {e}"
        except Exception as e:  # noqa: BLE001 - graceful by design
            status[p.name] = f"failed: {type(e).__name__}: {str(e)[:120]}"
        log(logger, "trend provider failed", logging.WARNING, provider=p.name, status=status[p.name])
        return []

    for items in await asyncio.gather(*(one(p) for p in providers())):
        results.extend(items)
    return results, status