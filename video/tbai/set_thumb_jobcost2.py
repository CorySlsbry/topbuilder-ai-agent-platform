"""Attach the custom thumbnail to the just-uploaded job-costing long-form.
Same token/creds pattern and CHANNEL-LOCK as yt_upload.py — refuses if the token
resolves to any channel other than Top Builder.
"""
import pathlib
import sys

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
TOKDIR = pathlib.Path.home() / ".youtube-tokens"
TOKEN = "topbuilderos"
EXPECT_CHANNEL = "UC3DHSlPj2uYkusfutAafyYA"      # Top Builder
VIDEO_ID = "_RqH39F4Gr0"
THUMB = pathlib.Path(__file__).parent / "build" / "jobcost2_thumb.jpg"


def creds_for(name: str) -> Credentials:
    p = TOKDIR / f"{name}.json"
    c = Credentials.from_authorized_user_file(str(p), SCOPES)
    if not c.valid and c.refresh_token:
        c.refresh(Request())
        p.write_text(c.to_json(), encoding="utf-8")
    return c


def main() -> int:
    if not THUMB.is_file():
        print(f"missing thumbnail: {THUMB}")
        return 2
    yt = build("youtube", "v3", credentials=creds_for(TOKEN))

    # ⛔ CHANNEL-LOCK before touching anything.
    me = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
    if not me or me[0]["id"] != EXPECT_CHANNEL:
        got = me[0]["id"] if me else "none"
        print(f"CHANNEL MISMATCH: token resolves to {got}, expected {EXPECT_CHANNEL}. Refusing.")
        return 2
    print(f"channel-lock OK: {me[0]['snippet']['title']} ({me[0]['id']})")

    yt.thumbnails().set(videoId=VIDEO_ID,
                        media_body=MediaFileUpload(str(THUMB))).execute()
    print(f"THUMBNAIL SET -> https://youtu.be/{VIDEO_ID}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
