"""
Generate OAuth refresh token with all required YouTube scopes.
Run this LOCALLY (not on GitHub Actions).
It will open a browser for you to authorize.

Required scopes:
- youtube (upload, manage videos)
- youtube.readonly (read channel stats)  
- yt-analytics.readonly (analytics data)

Usage:
  python scripts/generate_oauth_token.py
"""

import os
import json
from pathlib import Path

CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
]

def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET env vars first")
        print("\nSet them like this before running:")
        print("  Windows: set YOUTUBE_CLIENT_ID=your_client_id")
        print("           set YOUTUBE_CLIENT_SECRET=your_client_secret")
        print("  Git Bash: export YOUTUBE_CLIENT_ID=your_client_id")
        print("            export YOUTUBE_CLIENT_SECRET=your_client_secret")
        return

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Installing required package...")
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "pip", "install",
                       "google-auth-oauthlib", "google-api-python-client", "-q"])
        from google_auth_oauthlib.flow import InstalledAppFlow

    client_config = {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)

    print("\n" + "="*50)
    print("Opening browser for YouTube authorization...")
    print("Select your FitFacts YouTube channel account")
    print("="*50 + "\n")

    creds = flow.run_local_server(port=8080, open_browser=True)

    print("\n" + "="*50)
    print("✅ Authorization successful!")
    print("="*50)
    print(f"\nREFRESH TOKEN (copy this to GitHub Secrets as YOUTUBE_REFRESH_TOKEN):")
    print(f"\n{creds.refresh_token}\n")
    print("="*50)

    # Also save to file as backup
    token_file = Path("tmp/youtube_token.json")
    token_file.parent.mkdir(exist_ok=True)
    token_file.write_text(json.dumps({
        "refresh_token": creds.refresh_token,
        "client_id": CLIENT_ID,
        "scopes": SCOPES,
    }, indent=2))
    print(f"Also saved to: {token_file}")
    print("\nUpdate YOUTUBE_REFRESH_TOKEN in GitHub Secrets with the token above.")

if __name__ == "__main__":
    main()
