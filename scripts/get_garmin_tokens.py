"""
get_garmin_tokens.py
Run this ONCE on your local machine to generate Garmin auth tokens.
Then paste the output into GitHub Secrets as GARMIN_TOKENS.

Install first:
  pip install garminconnect --break-system-packages
"""

import json, sys, os
from pathlib import Path

try:
    from garminconnect import Garmin
except ImportError:
    print("Please install garminconnect first:")
    print("  pip install garminconnect --break-system-packages")
    sys.exit(1)

email    = input("Garmin email: ").strip()
password = input("Garmin password: ").strip()

token_dir = Path.home() / ".garminconnect"
token_dir.mkdir(exist_ok=True)

print("\nLogging in to Garmin Connect...")
print("(You may be prompted for a 2FA code if enabled)\n")

try:
    client = Garmin(email=email, password=password)
    client.login()
    # Explicitly save tokens to our directory
    client.garth.dump(str(token_dir))
    print("✅ Login successful — tokens saved!")
except Exception as e:
    print(f"❌ Login failed: {e}")
    sys.exit(1)

# Read all token files back
token_data = {}
for f in token_dir.iterdir():
    if f.is_file():
        try:
            token_data[f.name] = f.read_text()
        except Exception:
            pass

if not token_data:
    print("❌ No token files found — trying alternate path...")
    # garth sometimes saves to ~/.garth
    alt_dir = Path.home() / ".garth"
    if alt_dir.exists():
        for f in alt_dir.iterdir():
            if f.is_file():
                try:
                    token_data[f.name] = f.read_text()
                except Exception:
                    pass

if not token_data:
    print("❌ Still no tokens found. Listing home directory for debug:")
    for p in Path.home().iterdir():
        if p.name.startswith(".garmin") or p.name.startswith(".garth"):
            print(f"  {p}")
    sys.exit(1)

token_json = json.dumps(token_data)
print(f"\n✅ Found {len(token_data)} token file(s): {list(token_data.keys())}")
print("\n" + "="*60)
print("COPY EVERYTHING BETWEEN THE LINES INTO GITHUB SECRETS")
print("Secret name: GARMIN_TOKENS")
print("="*60)
print(token_json)
print("="*60)
