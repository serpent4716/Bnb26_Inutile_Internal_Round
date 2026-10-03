"""YouTube upload (OAuth installed-app flow, private by default) + dry run."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from ..config import MissingConfig, settings

UNVERIFIED_NOTICE = ("Uploads from an unverified Google Cloud OAuth app are locked to PRIVATE by YouTube, "
                     "regardless of the privacy you request. Change visibility in YouTube Studio, or get the "
                     "app audited by Google to publish publicly via the API.")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def youtube_configured() -> tuple[bool, str]:
    if not settings.youtube_client_secrets or not Path(settings.youtube_client_secrets).exists():
        return False, "set YOUTUBE_CLIENT_SECRETS to your OAuth client_secret.json (Desktop app)"
    try:
        import google_auth_oauthlib  # noqa: F401
        import googleapiclient  # noqa: F401
    except ImportError:
        return False, "install google-api-python-client google-auth-oauthlib"
    return True, ""


def _credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token = settings.data_dir / "youtube_token.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(settings.youtube_client_secrets, SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)   # opens a browser on the server machine
        token.write_text(creds.to_json())
    return creds


async def youtube_upload(video_path: str, title: str, description: str, tags: list[str],
                         privacy: str = "private") -> str:
    ok, why = youtube_configured()
    if not ok:
        raise MissingConfig("YOUTUBE_CLIENT_SECRETS", why)

    def work() -> str:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        yt = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
        body = {"snippet": {"title": title[:100], "description": description[:4900],
                            "tags": [t.lstrip("#") for t in tags][:15], "categoryId": "22"},
                "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
        req = yt.videos().insert(part="snippet,status", body=body,
                                 media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True))
        resp = None
        while resp is None:
            _, resp = req.next_chunk()
        return f"https://youtube.com/shorts/{resp['id']}"

    return await asyncio.to_thread(work)


def dry_run_url() -> str:
    return f"https://youtube.com/shorts/DRYRUN-{uuid.uuid4().hex[:11]}"
