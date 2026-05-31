"""
One-time script to get YouTube OAuth refresh token.
Run this ONCE on your laptop — saves refresh token to use in GitHub Actions.

Usage:
    pip install google-auth-oauthlib google-api-python-client
    python scripts/get_youtube_token.py
"""

import json
import os
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Paste your credentials here when running locally
# Get from: console.cloud.google.com → APIs → Credentials
CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "YOUR_CLIENT_ID_HERE")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "YOUR_CLIENT_SECRET_HERE")

CLIENT_CONFIG = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
    }
}


def main():
    print("=" * 50)
    print("YouTube OAuth Token Generator")
    print("=" * 50)
    print("\nThis will open your browser for Google login.")
    print("Login with the YouTube account you want to post to.\n")

    flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
    # Desktop app uses run_local_server or run_console
    try:
        creds = flow.run_local_server(port=8080)
    except Exception:
        # Fallback — copy-paste method if browser doesn't open
        creds = flow.run_console()

    print("\n✅ Authentication successful!")
    print("\n" + "=" * 50)
    print("COPY THESE TO GITHUB SECRETS:")
    print("=" * 50)
    print(f"\nYOUTUBE_CLIENT_ID:\n{CLIENT_CONFIG['installed']['client_id']}")
    print(f"\nYOUTUBE_CLIENT_SECRET:\n{CLIENT_CONFIG['installed']['client_secret']}")
    print(f"\nYOUTUBE_REFRESH_TOKEN:\n{creds.refresh_token}")
    print("\n" + "=" * 50)

    # Save locally too
    token_path = Path("tmp/youtube_token.json")
    token_path.parent.mkdir(exist_ok=True)
    token_data = {
        "client_id": CLIENT_CONFIG["installed"]["client_id"],
        "client_secret": CLIENT_CONFIG["installed"]["client_secret"],
        "refresh_token": creds.refresh_token,
    }
    token_path.write_text(json.dumps(token_data, indent=2))
    print(f"Token also saved to: {token_path}")


if __name__ == "__main__":
    main()
