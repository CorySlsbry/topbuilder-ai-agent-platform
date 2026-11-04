"""Upload + publish a video to a NAMED YouTube channel via the Data API v3 (resumable).
Hands-free once yt_auth.py has saved that channel's token. Reusable for any channel (neuron, autoadvisor, ...).

Usage:
  python yt_upload.py --channel neuron --file out.mp4 --title "..." --desc-file desc.txt \
                      --tags "a,b,c" --privacy public [--category 28] [--made-for-kids false]

Notes:
- Sets title/description/tags/categoryId + privacy + selfDeclaredMadeForKids=false.
- The AI/"altered content" disclosure is NOT settable via the Data API today — disclose in the description
  (this pipeline does) and/or toggle "Altered content -> Yes" once in Studio if you want the formal label.
- Token: ~/.youtube-tokens/<channel>.json (run yt_auth.py <channel> first).
"""
import argparse, pathlib, time, socket
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

socket.setdefaulttimeout(600)  # long socket timeout so big-chunk writes don't time out

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
TOKDIR = pathlib.Path.home() / ".youtube-tokens"

def creds_for(name):
    p = TOKDIR / f"{name}.json"
    if not p.exists():
        raise SystemExit(f"No token for '{name}'. Run:  python yt_auth.py {name}")
    c = Credentials.from_authorized_user_file(str(p), SCOPES)
    if not c.valid and c.refresh_token:
        c.refresh(Request()); p.write_text(c.to_json(), encoding="utf-8")
    return c

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--desc-file", required=True)
    ap.add_argument("--tags", default="")
    ap.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    ap.add_argument("--category", default="28")  # 28 = Science & Technology
    ap.add_argument("--made-for-kids", default="false")
    a = ap.parse_args()
    yt = build("youtube", "v3", credentials=creds_for(a.channel))
    # confirm the channel before posting (safety)
    me = yt.channels().list(part="snippet", mine=True).execute()
    print("Posting to channel:", me["items"][0]["snippet"]["title"])
    body = {
        "snippet": {"title": a.title[:100], "description": pathlib.Path(a.desc_file).read_text(encoding="utf-8"),
                    "tags": [t.strip() for t in a.tags.split(",") if t.strip()], "categoryId": a.category},
        "status": {"privacyStatus": a.privacy, "selfDeclaredMadeForKids": a.made_for_kids.lower() == "true"},
    }
    media = MediaFileUpload(a.file, resumable=True, chunksize=4 * 1024 * 1024)  # smaller chunks survive flaky networks
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None; tries = 0
    while resp is None:
        try:
            status, resp = req.next_chunk()
            if status:
                print(f"  upload {int(status.progress() * 100)}%")
        except HttpError as e:
            tries += 1
            if e.resp.status in (500, 502, 503, 504) and tries < 10:
                print(f"  transient HTTP {e.resp.status}, retry {tries}..."); time.sleep(5); continue
            raise
        except (TimeoutError, ConnectionError, OSError) as e:
            tries += 1
            if tries < 10:
                print(f"  network error ({type(e).__name__}), retry {tries}..."); time.sleep(5); continue
            raise
    print("PUBLISHED -> https://youtu.be/" + resp["id"], "(" + a.privacy + ", channel " + a.channel + ")")

if __name__ == "__main__":
    main()
