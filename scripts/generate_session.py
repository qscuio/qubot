import os
import asyncio
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv

# Load existing .env if present
load_dotenv()

async def generate_session():
    print("🔐 Telethon Session Generator")
    print("----------------------------")

    api_id = os.getenv("API_ID")
    if not api_id:
        api_id = input("Enter API_ID: ").strip()
    
    api_hash = os.getenv("API_HASH")
    if not api_hash:
        api_hash = input("Enter API_HASH: ").strip()

    if not api_id or not api_hash:
        print("❌ Error: API_ID and API_HASH are required.")
        return

    print("\nCheck your Telegram for the login code...")
    
    async with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        session_string = client.session.save()
        print("\n✅ Session String generated successfully!")
        print("\n" + session_string)
        print("\n⚠️  Copy this string and set it as SESSION (or TG_SESSION) in your .env file or GitHub Secrets.")
        print("   Do not share this string with anyone!")

if __name__ == "__main__":
    try:
        asyncio.run(generate_session())
    except ImportError:
        print("❌ Telethon is not installed. Run: pip install telethon")
    except Exception as e:
        print(f"❌ Error: {e}")
