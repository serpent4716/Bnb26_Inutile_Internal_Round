"""PublishAgent: YouTube (real upload or dry run) + export package for TikTok/Instagram (never auto-posted)."""
from __future__ import annotations

import json
import shutil

from ..config import settings
from ..providers import publish as yt
from ..schemas import AssemblyOutput, PublishOutput, PublishRequest, PublishTarget, ScriptOutput
from .edl import build_srt, write_text


def credits(asm: AssemblyOutput) -> list[dict]:
    seen, out = set(), []
    for seg in asm.edl.video:
        a = seg.attribution
        k = (a.provider, a.source_url or seg.source.path)
        if k not in seen:
            seen.add(k)
            out.append({"scene": seg.scene_id, **a.model_dump()})
    if asm.edl.music and asm.edl.music.attribution:
        out.append({"scene": "music", **asm.edl.music.attribution.model_dump()})
    return out


def credits_text(asm: AssemblyOutput) -> str:
    lines = [f"- {c['provider']}: {c['author'] or 'unknown'} {c['source_url']}".rstrip()
             for c in credits(asm) if c["provider"] not in ("demo_assets",)]
    return ("\n\nFootage credits:\n" + "\n".join(lines)) if lines else ""


async def run(run_id: str, req: PublishRequest, script: ScriptOutput, asm: AssemblyOutput) -> PublishOutput:
    title = req.title or script.title
    tags = req.hashtags or script.hashtags
    desc = (req.description or script.description) + "\n\n" + " ".join(tags) + credits_text(asm)

    if req.target == PublishTarget.youtube:
        if req.dry_run:
            return PublishOutput(target=req.target, dry_run=True, url=yt.dry_run_url(), privacy="private",
                                 notice="Dry run: nothing was uploaded. " + yt.UNVERIFIED_NOTICE)
        url = await yt.youtube_upload(asm.video_path, title, desc, tags, privacy="private")
        return PublishOutput(target=req.target, dry_run=False, url=url, privacy="private",
                             notice=yt.UNVERIFIED_NOTICE)

    # Export-only package
    out = settings.runs_dir / run_id / "export"
    out.mkdir(parents=True, exist_ok=True)
    mp4 = out / "short.mp4"
    shutil.copy(asm.video_path, mp4)
    srt = write_text(out / "captions.srt", build_srt(asm.edl))
    meta = write_text(out / "metadata.json", json.dumps({
        "title": title, "description": desc, "hashtags": tags, "duration_sec": asm.edl.total_duration,
        "resolution": f"{asm.edl.width}x{asm.edl.height}", "attributions": credits(asm),
        "targets": {"tiktok": "export-only, upload manually", "instagram_reels": "export-only, upload manually"},
    }, indent=2))
    return PublishOutput(target=req.target, dry_run=req.dry_run, export_dir=str(out),
                         files=[str(mp4), srt, meta],
                         notice="Export package only. TikTok and Instagram are not auto-posted; upload these files manually.")
