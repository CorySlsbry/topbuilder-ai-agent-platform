import pathlib, sys, time
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
TOKDIR = pathlib.Path.home() / ".youtube-tokens"
p = TOKDIR / "topbuilderos.json"
c = Credentials.from_authorized_user_file(str(p), SCOPES)
if not c.valid and c.refresh_token:
    c.refresh(Request())
    p.write_text(c.to_json(), encoding="utf-8")
yt = build("youtube", "v3", credentials=c)
VID = "cj5cB2ElUwo"

for i in range(30):
    resp = yt.videos().list(part="snippet,contentDetails,processingDetails", id=VID).execute()
    item = resp["items"][0]
    dur = item["contentDetails"]["duration"]
    pstatus = item.get("processingDetails", {}).get("processingStatus")
    pub = item["snippet"]["publishedAt"]
    print(f"[{i}] duration={dur} processingStatus={pstatus} publishedAt={pub}", flush=True)
    if dur != "P0D":
        print("DONE")
        print("FINAL_DURATION="+dur)
        print("FINAL_PUBLISHED="+pub)
        break
    time.sleep(20)
else:
    print("TIMEOUT still P0D")
