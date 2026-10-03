"""Trend-to-Short settings. Read from CreatorAi's backend/.env; every model name and limit comes from the
environment, never from code. Shared keys (GEMINI_API_KEY, GROQ_API_KEY, PEXELS_API_KEY) are reused as-is."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PKG = Path(__file__).resolve().parent              # app/trendshort
BACKEND = PKG.parents[1]                           # CreatorAi backend/
load_dotenv(BACKEND / ".env")


_MODEL_FALLBACK = {"GEMINI_MODEL": "GEMINI_TEXT_MODEL"}  # reuse CreatorAi's Gemini model if ours isn't set


def _model(name: str) -> str:
    """Clean model ids pasted from docs/consoles: quotes, spaces, inline comments, Gemini's 'models/' prefix."""
    raw = os.getenv(name) or os.getenv(_MODEL_FALLBACK.get(name, ""), "")
    v = raw.split("#")[0].strip().strip('"').strip("'").strip()
    if name == "GEMINI_MODEL" and v.startswith("models/"):
        v = v[len("models/"):]
    return v


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


class MissingConfig(RuntimeError):
    """Raised with the exact env var name the user needs to set."""

    def __init__(self, var: str, hint: str = ""):
        super().__init__(f"Missing env var {var}. {hint}".strip())
        self.var = var


@dataclass(frozen=True)
class Settings:
    mock_mode: bool = field(default_factory=lambda: _bool("T2S_MOCK_MODE", _bool("MOCK_MODE", False)))
    llm_mock_fallback: bool = field(default_factory=lambda: _bool("LLM_MOCK_FALLBACK", False))

    # LLM chain (models are env-only on purpose)
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: _model("GEMINI_MODEL"))
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_model: str = field(default_factory=lambda: _model("GROQ_MODEL"))
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    openrouter_model: str = field(default_factory=lambda: _model("OPENROUTER_MODEL"))
    ollama_host: str = field(default_factory=lambda: os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: _model("OLLAMA_MODEL"))
    llm_order: str = field(default_factory=lambda: os.getenv("LLM_ORDER", "gemini,groq,openrouter,ollama"))

    # TTS
    tts_order: str = field(default_factory=lambda: os.getenv("TTS_ORDER", "edge,piper,kokoro"))
    edge_voice: str = field(default_factory=lambda: os.getenv("EDGE_TTS_VOICE", "en-US-AndrewNeural"))
    edge_rate: str = field(default_factory=lambda: os.getenv("EDGE_TTS_RATE", "+8%"))
    piper_bin: str = field(default_factory=lambda: os.getenv("PIPER_BIN", "piper"))
    piper_model: str = field(default_factory=lambda: os.getenv("PIPER_MODEL", ""))
    kokoro_voice: str = field(default_factory=lambda: os.getenv("KOKORO_VOICE", "af_heart"))

    # Captions
    whisper_model: str = field(default_factory=lambda: os.getenv("WHISPER_MODEL") or os.getenv("WHISPER_LOCAL_MODEL", "base"))
    whisper_enabled: bool = field(default_factory=lambda: _bool("WHISPER_ENABLED", True))

    # Footage
    pexels_api_key: str = field(default_factory=lambda: os.getenv("PEXELS_API_KEY", ""))
    pixabay_api_key: str = field(default_factory=lambda: os.getenv("PIXABAY_API_KEY", ""))
    music_path: str = field(default_factory=lambda: os.getenv("MUSIC_PATH", ""))

    # Trends / publish
    youtube_api_key: str = field(default_factory=lambda: os.getenv("YOUTUBE_API_KEY", ""))
    youtube_client_secrets: str = field(default_factory=lambda: os.getenv("YOUTUBE_CLIENT_SECRETS", ""))
    reddit_subreddits: str = field(default_factory=lambda: os.getenv("REDDIT_SUBREDDITS", "popular,todayilearned,technology"))
    reddit_client_id: str = field(default_factory=lambda: os.getenv("REDDIT_CLIENT_ID", ""))
    reddit_client_secret: str = field(default_factory=lambda: os.getenv("REDDIT_CLIENT_SECRET", ""))
    trend_all_regions: str = field(default_factory=lambda: os.getenv("TREND_ALL_REGIONS", "US,IN,GB"))
    reddit_user_agent: str = field(default_factory=lambda: os.getenv("REDDIT_USER_AGENT", "trend-to-short/0.1 (local demo)"))
    trend_cache_minutes: float = field(default_factory=lambda: _float("TREND_CACHE_MINUTES", 30))
    # Comma-separated subset of: youtube, google_trends, reddit
    trend_sources: str = field(default_factory=lambda: os.getenv("TREND_SOURCES", "youtube"))

    # Paths
    # Not under media/: CreatorAi serves that folder publicly, and this holds the SQLite db and OAuth token.
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("T2S_DATA_DIR", str(BACKEND / "data" / "trendshort"))))
    demo_assets: Path = field(default_factory=lambda: Path(os.getenv("T2S_DEMO_ASSETS", str(PKG / "demo_assets"))))
    database_url: str = field(default_factory=lambda: os.getenv("T2S_DATABASE_URL", ""))

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'app.db'}"

    def rate_limit_rpm(self, provider: str) -> float:
        """Requests/minute for a provider. 0 = no fixed pacing (still serialized, still backs off on 429).
        Values live in .env because free-tier limits change."""
        return _float(f"RATE_{provider.upper()}_RPM", 0)


settings = Settings()
for p in (settings.data_dir, settings.cache_dir, settings.runs_dir):
    p.mkdir(parents=True, exist_ok=True)


def _windows_saved_path() -> str:
    """PATH as stored in the registry, so a freshly installed FFmpeg is found even if this
    process was started from a terminal opened before the install."""
    try:
        import winreg
    except ImportError:
        return ""
    parts = []
    for hive, key in ((winreg.HKEY_CURRENT_USER, r"Environment"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
        try:
            with winreg.OpenKey(hive, key) as k:
                parts.append(os.path.expandvars(winreg.QueryValueEx(k, "Path")[0]))
        except OSError:
            pass
    return os.pathsep.join(parts)


@lru_cache(maxsize=None)
def find_tool(name: str) -> str | None:
    """Locate ffmpeg/ffprobe: FFMPEG_DIR env, PATH, saved Windows PATH, then winget install dirs."""
    custom = os.getenv("FFMPEG_DIR", "")
    if custom and (hit := shutil.which(name, path=custom)):
        return hit
    if hit := shutil.which(name) or shutil.which(name, path=_windows_saved_path() or None):
        return hit
    local = os.getenv("LOCALAPPDATA", "")
    if local:
        links = Path(local) / "Microsoft" / "WinGet" / "Links"
        if hit := shutil.which(name, path=str(links)):
            return hit
        for exe in sorted((Path(local) / "Microsoft" / "WinGet" / "Packages").glob(f"*FFmpeg*/**/bin/{name}.exe")):
            return str(exe)
    return None


def require_ffmpeg() -> str:
    path = find_tool("ffmpeg")
    if not path or not find_tool("ffprobe"):
        find_tool.cache_clear()  # allow a later retry to pick up a fresh install
        raise MissingConfig("FFMPEG_DIR", "ffmpeg/ffprobe not found. Install FFmpeg (Windows: "
                            "`winget install Gyan.FFmpeg`; macOS: `brew install ffmpeg`; Linux: `apt install ffmpeg`) "
                            "or set FFMPEG_DIR to the folder containing ffmpeg and ffprobe.")
    return path


def ffprobe_bin() -> str:
    require_ffmpeg()
    return find_tool("ffprobe")  # type: ignore[return-value]