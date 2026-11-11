#!/usr/bin/env python3
"""Send one message from the logged-in account.
  send.py @username "text"
Do not run while userbot.py is running (shared session file -> "database is locked").
"""
import asyncio
import sys

from telethon import TelegramClient

import userbot as u


async def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    target, text = sys.argv[1], " ".join(sys.argv[2:])
    client = TelegramClient(str(u.STATE_DIR / "account"), u.CFG["api_id"], u.CFG["api_hash"])
    await client.connect()
    try:
        if not await client.is_user_authorized():
            sys.exit("не авторизован: сначала login.py")
        msg = await client.send_message(target, text)
        print(f"отправлено {target}: id={msg.id}")
    finally:
        await client.disconnect()


asyncio.run(main())
