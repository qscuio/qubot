#!/usr/bin/env python3
import os
import sys
from pathlib import Path

from telethon import TelegramClient, events
from telethon.sessions import StringSession


def _load_env_file(path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _get_required(key):
    value = os.environ.get(key)
    if not value:
        print(f"Missing env var: {key}", file=sys.stderr)
        sys.exit(2)
    return value


async def main():
    _load_env_file(Path(__file__).resolve().parents[1] / ".env")

    api_id = int(_get_required("API_ID"))
    api_hash = _get_required("API_HASH")
    session = (
        os.environ.get("TELETHON_SESSION")
        or os.environ.get("TG_SESSION")
        or os.environ.get("SESSION")
        or ""
    )
    use_login = "--login" in sys.argv
    if not session and not use_login:
        print("Missing TELETHON_SESSION (or TG_SESSION) in env/.env", file=sys.stderr)
        sys.exit(2)

    try:
        session_obj = StringSession(session) if session else StringSession()
    except ValueError:
        if not use_login:
            print(
                "Session string is not compatible with Telethon.\n"
                "Set TELETHON_SESSION (Telethon format) or rerun with --login.",
                file=sys.stderr
            )
            sys.exit(2)
        session_obj = StringSession()

    client = TelegramClient(session_obj, api_id, api_hash)
    if use_login:
        await client.start()
        if os.environ.get("PRINT_SESSION") == "1":
            print(f"TELETHON_SESSION={client.session.save()}")
    else:
        await client.connect()

    if not await client.is_user_authorized():
        print("Session is not authorized. Run with --login to create one.", file=sys.stderr)
        await client.disconnect()
        sys.exit(3)

    me = await client.get_me()
    print(f"Logged in as {me.username or me.first_name or me.id} (bot={me.bot})")

    dialogs = await client.get_dialogs()
    print(f"Dialogs: {len(dialogs)}")
    if os.environ.get("PRINT_DIALOGS") == "1":
        for dialog in dialogs:
            title = dialog.title or dialog.name or dialog.username or "Unknown"
            is_group = getattr(dialog, "is_group", False)
            is_channel = getattr(dialog, "is_channel", False)
            print(f"- {title} (id={dialog.id}, group={is_group}, channel={is_channel})")

    @client.on(events.NewMessage)
    async def on_message(event):
        msg = event.message
        text = (msg.raw_text or "").replace("\n", " ").strip()
        if not text:
            text = "<no text>"
        text = text[:160]
        chat = await event.get_chat()
        title = getattr(chat, "title", None) or getattr(chat, "username", None) or "unknown"
        print(f"[msg] chat={title} chat_id={event.chat_id} out={msg.out} text={text}")

    if os.environ.get("RAW_UPDATES") == "1":
        @client.on(events.Raw)
        async def on_raw(event):
            print(f"[raw] {event.__class__.__name__}")

    print("Listening for new messages... (Ctrl+C to stop)")
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        import asyncio
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
