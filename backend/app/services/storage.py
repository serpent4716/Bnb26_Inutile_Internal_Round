"""Media storage. Files always land locally first (FFmpeg needs a path), then publish()
exposes them via STORAGE_BACKEND: "local" serves /media/... through StaticFiles,
"cloudinary" uploads and returns the secure URL.
"""

import asyncio
import re
import shutil
from pathlib import Path

from fastapi import UploadFile

from app.config import settings

MEDIA_DIR = Path(__file__).resolve().parents[2] / "media"
MEDIA_DIR.mkdir(exist_ok=True)

if settings.STORAGE_BACKEND == "cloudinary":
    import cloudinary
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


def safe_name(name: str | None) -> str:
    return re.sub(r"[^\w.\-]+", "_", Path(name or "").name)[-120:] or "upload"


def asset_dir(asset_id: str) -> Path:
    """Local work dir for one asset: original, thumb.jpg, audio.wav, keyframes/."""
    d = MEDIA_DIR / "assets" / asset_id
    d.mkdir(parents=True, exist_ok=True)
    return d


async def save_upload(file: UploadFile, asset_id: str) -> Path:
    """Stream an upload to the asset's work dir. Returns the local path."""
    path = asset_dir(asset_id) / safe_name(file.filename)
    with path.open("wb") as f:
        await asyncio.to_thread(shutil.copyfileobj, file.file, f)
    return path


async def publish(path: Path, folder: str) -> str:
    """Make a local file reachable by URL. Returns storage_url (relative /media/... for local)."""
    if settings.STORAGE_BACKEND == "cloudinary":
        res = await asyncio.to_thread(
            cloudinary.uploader.upload_large, str(path),
            resource_type="auto", folder=f"creatorai/{folder}", use_filename=True,
        )
        return res["secure_url"]
    return "/media/" + path.relative_to(MEDIA_DIR).as_posix()
