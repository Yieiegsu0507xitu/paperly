#!/usr/bin/env python3
"""
Automated Firebase Cloud Messaging (FCM) Notification Broadcaster
Triggered by GitHub Actions on push when WallpaperLY catalog is updated.
Broadcasts a push notification to all WallpaperLY users subscribed to topic 'wallpapers'.
"""

import os
import sys
import json
import subprocess
import random

# Ensure UTF-8 output encoding across all operating systems
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

def find_catalog_file():
    candidates = ["paperly.json", "Paperly.json", "catalog.json"]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

def extract_added_wallpapers(catalog_path):
    """
    Extracts newly added wallpapers by comparing current catalog with previous git commit (HEAD~1).
    Wallpapers whose URL did not exist in HEAD~1 are the newly added ones.
    """
    added_wallpapers = []
    
    # Method 1: Compare HEAD~1 catalog JSON with current catalog (exact URL set difference)
    try:
        old_content = subprocess.check_output(
            ["git", "show", f"HEAD~1:{catalog_path}"],
            text=True,
            stderr=subprocess.DEVNULL
        )
        old_catalog = json.loads(old_content)
        old_urls = {
            w.get("url").strip() for w in old_catalog
            if isinstance(w, dict) and w.get("url")
        }
        
        with open(catalog_path, "r", encoding="utf-8") as f:
            new_catalog = json.load(f)
            
        for item in new_catalog:
            if isinstance(item, dict) and item.get("url"):
                if item.get("url").strip() not in old_urls:
                    added_wallpapers.append(item)
                    
        if added_wallpapers:
            print(f"Detected {len(added_wallpapers)} new wallpaper(s) via URL comparison against HEAD~1.")
            return added_wallpapers
    except Exception as e:
        print(f"git show HEAD~1 comparison unavailable ({e}), trying git diff...")

    # Method 2: Git diff line check
    try:
        diff_cmd = ["git", "diff", "HEAD~1", "HEAD", "--", catalog_path]
        diff_output = subprocess.check_output(diff_cmd, text=True, stderr=subprocess.DEVNULL)
        added_lines = [line[1:].strip() for line in diff_output.splitlines() if line.startswith("+") and not line.startswith("+++")]
        diff_content = "\n".join(added_lines)

        with open(catalog_path, "r", encoding="utf-8") as f:
            full_catalog = json.load(f)

        for item in full_catalog:
            url = item.get("url", "")
            if url and url in diff_content:
                added_wallpapers.append(item)
        if added_wallpapers:
            return added_wallpapers
    except Exception:
        pass

    # Method 3: Fallback if no git history (e.g. fresh clone / initial commit)
    if not added_wallpapers:
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    added_wallpapers = [data[0]]
        except Exception as e:
            print(f"Error reading catalog: {e}")

    return added_wallpapers

# Clean, engaging notification templates rotated across uploads
NOTIFICATION_TEMPLATES = [
    ("New Wallpapers Added 🎨", "Tap to view the latest wallpapers."),
    ("Fresh Wallpapers Arrived ✨", "Tap to check them out!"),
    ("New Wallpapers Are Here! 🚀", "Discover the latest wallpapers in WallpaperLY."),
    ("Fresh Wallpapers Just Dropped 💫", "Give your screen a fresh new look."),
    ("We've Added Fresh Wallpapers ✨", "Tap to explore them."),
    ("New Wallpapers Just Landed 🖼️", "Fresh picks are waiting for you.")
]

def build_notification_content(added_wallpapers):
    count = len(added_wallpapers)
    if count == 0:
        return None

    first = added_wallpapers[0]
    image_url = first.get("thumbnail") or first.get("url")

    title, body = random.choice(NOTIFICATION_TEMPLATES)

    return {
        "title": title,
        "body": body,
        "image_url": image_url,
        "count": count
    }

def send_fcm_notification(project_id, service_account_json_str, content):
    """
    Sends notification using Google OAuth2 and FCM HTTP v1 API.
    """
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        import requests
    except ImportError:
        print("Required libraries missing. Install: pip install google-auth requests")
        return False

    try:
        service_account_info = json.loads(service_account_json_str)
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/firebase.messaging"]
        )
        credentials.refresh(Request())
        access_token = credentials.token
    except Exception as e:
        print(f"Failed to authenticate with Firebase Service Account: {e}")
        return False

    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; UTF-8",
    }

    payload = {
        "message": {
            "topic": "wallpapers",
            "notification": {
                "title": content["title"],
                "body": content["body"]
            },
            "data": {
                "title": content["title"],
                "body": content["body"],
                "image_url": content["image_url"] or ""
            },
            "android": {
                "priority": "HIGH",
                "notification": {
                    "channel_id": "wallpaperly_new_wallpapers",
                    "default_sound": True,
                    "default_vibrate_timings": True
                }
            }
        }
    }

    if content["image_url"]:
        payload["message"]["notification"]["image"] = content["image_url"]
        payload["message"]["android"]["notification"]["image"] = content["image_url"]

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        print(f"Successfully broadcast FCM notification: {response.json()}")
        return True
    else:
        print(f"FCM error response ({response.status_code}): {response.text}")
        return False

def main():
    project_id = os.environ.get("FIREBASE_PROJECT_ID", "wallpaperly-37205")
    service_account_str = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()

    catalog_path = find_catalog_file()
    if not catalog_path:
        print("Could not find catalog file (paperly.json). Aborting.")
        sys.exit(0)

    print(f"Analyzing catalog: {catalog_path}")
    added = extract_added_wallpapers(catalog_path)
    if not added:
        print("No new wallpapers detected.")
        sys.exit(0)

    content = build_notification_content(added)
    print("\n--- Notification Preview ---")
    print(f"Title: {content['title']}")
    print(f"Body:  {content['body']}")
    print(f"Image: {content['image_url']}")
    print(f"Topic: wallpapers")
    print("----------------------------\n")

    if not service_account_str:
        print("NOTICE: FIREBASE_SERVICE_ACCOUNT_JSON secret is not set.")
        print("To enable automatic live push notifications:")
        print("1. Go to Firebase Console -> Project Settings -> Service Accounts")
        print("2. Click 'Generate new private key'")
        print("3. Add the JSON key content to GitHub Secrets as 'FIREBASE_SERVICE_ACCOUNT_JSON'")
        print("\nSimulation complete. Notification formatted successfully.")
        sys.exit(0)

    success = send_fcm_notification(project_id, service_account_str, content)
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
