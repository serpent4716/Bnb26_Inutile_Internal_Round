"""License-safe footage: Pexels -> Pixabay (video), then Pexels/Pixabay stills for a Ken Burns fallback,
then local demo assets. No AI video generation (by design)."""
from __future__ import annotations

import hashlib
import logging
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from ..cache import DiskCache
from ..config import settings
from ..ratelimit import limiter, raise_for_status, with_backoff
from ..schemas import Attribution, ClipCandidate

logger = logging.getLogger("t2s.footage")
PEXELS_LICENSE = "Pexels License (free to use, attribution appreciated) https://www.pexels.com/license/"
PIXABAY_LICENSE = "Pixabay Content License https://pixabay.com/service/license-summary/"


class FootageProvider(ABC):
    name: str

    @abstractmethod
    def configured(self) -> tuple[bool, str]: ...

    @abstractmethod
    async def search(self, query: str, n: int = 4) -> list[ClipCandidate]: ...


async def _get_json(provider: str, url: str, params: dict, headers: dict | None = None) -> dict:
    async def call():
        async with httpx.AsyncClient(timeout=20, headers=headers or {}) as c:
            r = await c.get(url, params=params)
        raise_for_status(provider, r.status_code, dict(r.headers), r.text[:300])
        return r.json()
    return await with_backoff(lambda: limiter(provider).run(call))


class PexelsVideo(FootageProvider):
    name = "pexels"

    def configured(self) -> tuple[bool, str]:
        return bool(settings.pexels_api_key), "missing key PEXELS_API_KEY"

    async def search(self, query: str, n: int = 4) -> list[ClipCandidate]:
        data = await _get_json("pexels", "https://api.pexels.com/videos/search",
                               {"query": query, "orientation": "portrait", "per_page": n, "size": "medium"},
                               {"Authorization": settings.pexels_api_key})
        out = []
        for v in data.get("videos", []):
            files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("height")]
            if not files:
                continue
            # prefer the smallest file that is still >= 1280 tall (fast download, sharp enough for 1080x1920)
            good = sorted([f for f in files if f["height"] >= 1280], key=lambda f: f["height"]) or \
                sorted(files, key=lambda f: -f["height"])
            f = good[0]
            slug = v.get("url", "").rstrip("/").split("/")[-1]
            out.append(ClipCandidate(
                kind="video", provider="pexels", url=f["link"], preview_url=v.get("image", ""),
                description=slug.replace("-", " "), width=f["width"], height=f["height"],
                duration_sec=float(v.get("duration", 0)),
                attribution=Attribution(provider="Pexels", author=v.get("user", {}).get("name", ""),
                                        author_url=v.get("user", {}).get("url", ""), source_url=v.get("url", ""),
                                        license=PEXELS_LICENSE)))
        return out


class PixabayVideo(FootageProvider):
    name = "pixabay"

    def configured(self) -> tuple[bool, str]:
        return bool(settings.pixabay_api_key), "missing key PIXABAY_API_KEY"

    async def search(self, query: str, n: int = 4) -> list[ClipCandidate]:
        data = await _get_json("pixabay", "https://pixabay.com/api/videos/",
                               {"key": settings.pixabay_api_key, "q": query[:100], "per_page": max(n, 3),
                                "safesearch": "true"})
        out = []
        for h in data.get("hits", [])[:n]:
            vids = h.get("videos", {})
            f = vids.get("large") if vids.get("large", {}).get("url") else vids.get("medium", {})
            if not f.get("url"):
                continue
            out.append(ClipCandidate(
                kind="video", provider="pixabay", url=f["url"], preview_url=h.get("videos", {}).get("tiny", {}).get("thumbnail", ""),
                description=h.get("tags", ""), width=f.get("width", 0), height=f.get("height", 0),
                duration_sec=float(h.get("duration", 0)),
                attribution=Attribution(provider="Pixabay", author=h.get("user", ""),
                                        author_url=f"https://pixabay.com/users/{h.get('user', '')}-{h.get('user_id', '')}/",
                                        source_url=h.get("pageURL", ""), license=PIXABAY_LICENSE)))
        return out


class StillsKenBurns(FootageProvider):
    """Free stock photos animated with zoom/pan at render time, so a scene is never blank."""
    name = "stills"

    def configured(self) -> tuple[bool, str]:
        ok = bool(settings.pexels_api_key or settings.pixabay_api_key)
        return ok, "needs PEXELS_API_KEY or PIXABAY_API_KEY"

    async def search(self, query: str, n: int = 3) -> list[ClipCandidate]:
        if settings.pexels_api_key:
            data = await _get_json("pexels", "https://api.pexels.com/v1/search",
                                   {"query": query, "orientation": "portrait", "per_page": n},
                                   {"Authorization": settings.pexels_api_key})
            return [ClipCandidate(
                kind="image", provider="pexels-photo", url=p["src"].get("large2x") or p["src"]["original"],
                preview_url=p["src"].get("medium", ""), description=p.get("alt", ""),
                width=p.get("width", 0), height=p.get("height", 0),
                attribution=Attribution(provider="Pexels", author=p.get("photographer", ""),
                                        author_url=p.get("photographer_url", ""), source_url=p.get("url", ""),
                                        license=PEXELS_LICENSE)) for p in data.get("photos", [])]
        data = await _get_json("pixabay", "https://pixabay.com/api/",
                               {"key": settings.pixabay_api_key, "q": query[:100], "orientation": "vertical",
                                "image_type": "photo", "per_page": max(n, 3), "safesearch": "true"})
        return [ClipCandidate(
            kind="image", provider="pixabay-photo", url=h["largeImageURL"], preview_url=h.get("previewURL", ""),
            description=h.get("tags", ""), width=h.get("imageWidth", 0), height=h.get("imageHeight", 0),
            attribution=Attribution(provider="Pixabay", author=h.get("user", ""), source_url=h.get("pageURL", ""),
                                    license=PIXABAY_LICENSE)) for h in data.get("hits", [])[:n]]


class DemoAssets(FootageProvider):
    """Committed local clips/images under demo_assets/ (generated, license-free)."""
    name = "demo"

    def configured(self) -> tuple[bool, str]:
        return (settings.demo_assets / "clips").exists(), "demo_assets/clips missing; run scripts/make_demo_assets.py"

    async def search(self, query: str, n: int = 3) -> list[ClipCandidate]:
        clips = sorted((settings.demo_assets / "clips").glob("*.mp4"))
        imgs = sorted((settings.demo_assets / "images").glob("*.jpg"))
        if not clips:
            return []
        h = int(hashlib.md5(query.encode()).hexdigest(), 16)
        picks = [clips[(h + i) % len(clips)] for i in range(min(2, len(clips)))]
        out = [ClipCandidate(kind="video", provider="demo", url=str(p), local_path=str(p),
                             description=p.stem.replace("_", " "), width=540, height=960, duration_sec=6,
                             attribution=Attribution(provider="demo_assets", author="generated locally",
                                                     license="Generated by FFmpeg for this repo (CC0)"))
               for p in picks]
        if imgs:
            p = imgs[h % len(imgs)]
            out.append(ClipCandidate(kind="image", provider="demo", url=str(p), local_path=str(p),
                                     description=p.stem.replace("_", " "), width=1080, height=1920,
                                     attribution=Attribution(provider="demo_assets", author="generated locally",
                                                             license="Generated by FFmpeg for this repo (CC0)")))
        return out[:n]


_ALL = {p.name: p for p in (PexelsVideo(), PixabayVideo(), StillsKenBurns(), DemoAssets())}


def chain() -> list[FootageProvider]:
    if settings.mock_mode:
        return [_ALL["demo"]]
    return [_ALL["pexels"], _ALL["pixabay"], _ALL["stills"], _ALL["demo"]]


def all_providers() -> list[FootageProvider]:
    return list(_ALL.values())


_dl_cache = DiskCache("media")


async def download(c: ClipCandidate) -> str:
    """Download (or reuse) a candidate's file. Cached by URL hash on disk."""
    if c.local_path and Path(c.local_path).exists():
        return c.local_path
    if Path(c.url).exists():
        return c.url
    ext = ".mp4" if c.kind == "video" else ".jpg"
    key = hashlib.sha256(c.url.encode()).hexdigest()[:24]
    dest = _dl_cache.path_for(key, ext)
    if dest.exists() and dest.stat().st_size > 0:
        return str(dest)
    lim = limiter(c.provider.split("-")[0])

    async def call():
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15), follow_redirects=True) as cl:
            async with cl.stream("GET", c.url) as r:
                raise_for_status(c.provider, r.status_code, dict(r.headers))
                tmp = dest.with_suffix(".part")
                with open(tmp, "wb") as f:
                    async for chunk in r.aiter_bytes(1 << 16):
                        f.write(chunk)
                shutil.move(tmp, dest)
        return str(dest)
    return await with_backoff(lambda: lim.run(call))
