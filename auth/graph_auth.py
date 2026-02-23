"""
Microsoft Graph OAuth authentication using MSAL.
Handles token acquisition and refresh via device flow.
"""

import os
import json
import msal
import argparse
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TOKEN_CACHE_PATH = Path.home() / ".arec_briefing_token_cache.json"

SCOPES = [
    "https://graph.microsoft.com/Calendars.Read",
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Tasks.Read",
]

def _load_cache():
    cache = msal.SerializableTokenCache()
    if TOKEN_CACHE_PATH.exists():
        cache.deserialize(TOKEN_CACHE_PATH.read_text())
    return cache

def _save_cache(cache):
    if cache.has_state_changed:
        TOKEN_CACHE_PATH.write_text(cache.serialize())

def _build_app(cache):
    return msal.PublicClientApplication(
        client_id=os.environ["AZURE_CLIENT_ID"],
        authority=f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}",
        token_cache=cache,
    )

def get_access_token() -> str:
    """Get a valid access token, refreshing silently if needed."""
    cache = _load_cache()
    app = _build_app(cache)
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_cache(cache)
            return result["access_token"]
    raise RuntimeError(
        "No cached token. Run: python3 auth/graph_auth.py --setup"
    )

def setup_auth():
    """Interactive device flow — run once to cache credentials."""
    cache = _load_cache()
    app = _build_app(cache)
    flow = app.initiate_device_flow(scopes=SCOPES)
    print(f"\n{'='*60}")
    print("MICROSOFT AUTHENTICATION")
    print(f"{'='*60}")
    print(f"\n{flow['message']}\n")
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" in result:
        _save_cache(cache)
        print("✓ Authentication successful.")
        r = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {result['access_token']}"}
        )
        user = r.json()
        print(f"✓ Signed in as: {user.get('displayName')} ({user.get('mail')})")
        print(f"\nAdd to your .env:")
        print(f"MS_USER_ID={user.get('id')}")
    else:
        print(f"✗ Failed: {result.get('error_description')}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true")
    args = parser.parse_args()
    if args.setup:
        setup_auth()
