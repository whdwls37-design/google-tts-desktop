"""Per-channel OAuth tokens. One Google OAuth client serves every channel."""

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# youtube.upload: videos.insert / thumbnails.set
# youtube.force-ssl: captions.insert and channels.list(mine=True)
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def login(client_secret: Path, token_path: Path) -> Credentials:
    """Opens a browser for consent. Pick the target channel on Google's chooser."""
    if not client_secret.exists():
        raise FileNotFoundError(
            f"OAuth client secret not found: {client_secret}\n"
            "Create a 'Desktop app' OAuth client in Google Cloud Console and download its JSON."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def load_credentials(token_path: Path) -> Credentials:
    if not token_path.exists():
        raise FileNotFoundError(
            f"No token at {token_path}. Run: python -m youtube_uploader auth <channel>"
        )
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise RuntimeError(
                f"Token at {token_path} is invalid. Re-run: python -m youtube_uploader auth <channel>"
            )
    return creds


def youtube_service(creds: Credentials):
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def whoami(service) -> dict:
    """Returns {'id', 'title'} of the channel the token belongs to."""
    resp = service.channels().list(part="id,snippet", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        raise RuntimeError("This Google account has no YouTube channel.")
    return {"id": items[0]["id"], "title": items[0]["snippet"]["title"]}
