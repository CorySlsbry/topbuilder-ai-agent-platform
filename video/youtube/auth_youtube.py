"""One-time YouTube Data API v3 OAuth bootstrap for the Salisbury Bookkeeping channel.

Opens the Google CONSENT SCREEN in your browser; you sign in as the channel's Google
account and click Allow. The refresh token is saved to token.json, after which posting
is fully automated (no further consent needed).

Setup:
  1. Place a Desktop OAuth client's JSON next to this file as: client_secret.json
  2. pip install google-auth-oauthlib google-api-python-client
  3. python auth_youtube.py     # browser opens the consent screen
"""
import pathlib
from google_auth_oauthlib.flow import InstalledAppFlow

HERE = pathlib.Path(__file__).parent
CLIENT = HERE / "client_secret.json"
TOKEN = HERE / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

if not CLIENT.exists():
    raise SystemExit(
        f"Missing {CLIENT}. Create a Desktop OAuth client in Google Cloud Console "
        f"(APIs & Services > Credentials > Create OAuth client ID > Desktop app), "
        f"download its JSON, and save it as client_secret.json here."
    )

flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES)
creds = flow.run_local_server(
    port=0,
    prompt="consent",
    access_type="offline",
    authorization_prompt_message="Opening the Google consent screen in your browser. Sign in as the Salisbury Bookkeeping account and click Allow...",
    success_message="Authorized. You can close this tab and return to the terminal.",
)
TOKEN.write_text(creds.to_json(), encoding="utf-8")
print(f"AUTHORIZED. Refresh token saved to {TOKEN}. Posting is now automated.")
