import os
from instagrapi import Client
from dotenv import load_dotenv

load_dotenv()

user = os.getenv("IG_USER_TE")
pwd = os.getenv("IG_PASS_TE")

print(f"🔄 Logging into @{user} with updated instagrapi...")
cl = Client()
# Force a fresh device ID to avoid IP flags
cl.set_device({"manufacturer": "Xiaomi", "model": "M2007J20CG", "android_version": 30, "android_release": "11"})

try:
    cl.login(user, pwd)
    print("✅ SUCCESS! Login bypassed the 'out of date' check.")
except Exception as e:
    print(f"❌ Failed: {e}")
