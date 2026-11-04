"""One-off: attach the custom thumbnail to the just-uploaded backoffice2 video (same token/creds
pattern as yt_upload.py, same channel-lock)."""
import pathlib, sys
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
TOKDIR = pathlib.Path.home() / ".youtube-tokens"
EXPECT_CHANNEL = "UCkApot-QB3kBq1UBEqXa34A"

def creds_for(name):
    p = TOKDIR / f"{name}.json"
    c = Credentials.from_authorized_user_file(str(p), SCOPES)
    if not c.valid and c.refresh_token:
        c.refresh(Request()); p.write_text(c.to_json(), encoding="utf-8")
    return c

if __name__ == "__main__":
    video_id, thumb_path = sys.argv[1], sys.argv[2]
    yt = build("youtube", "v3", credentials=creds_for("salisbury"))
    me = yt.channels().list(part="id", mine=True).execute()
    ch_id = me["items"][0]["id"]
    if ch_id != EXPECT_CHANNEL:
        raise SystemExit(f"CHANNEL-LOCK ABORT: resolves to {ch_id}, expected {EXPECT_CHANNEL}")
    media = MediaFileUpload(thumb_path)
    resp = yt.thumbnails().set(videoId=video_id, media_body=media).execute()
    print("THUMBNAIL SET:", resp)
