#!/usr/bin/env python3
"""Diagnostic: dump the last messages of the anonymous-chat bot, read-only."""
import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import userbot  # noqa: E402
from telethon import TelegramClient  # noqa: E402


async def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    session = sys.argv[2] if len(sys.argv) > 2 else str(userbot.STATE_DIR / "account")
    client = TelegramClient(session, userbot.CFG["api_id"], userbot.CFG["api_hash"])
    await client.start()
    me = await client.get_me()
    ent = await client.get_entity(userbot.CFG["anon_bot"])
    print(f"me={me.id} @{me.username} | bot={ent.id} @{ent.username} | anon_active={userbot.state.get('anon_active')} partner={userbot.state.get('anon_partner')}")
    msgs = [m async for m in client.iter_messages(ent.id, limit=limit)]
    for m in reversed(msgs):
        sender = "ME" if m.out else "BOT"
        markup = "markup" if m.reply_markup else ""
        sysmsg = "system" if userbot.is_anon_system(m) else "user"
        body = (m.raw_text or "").replace("\n", " ⏎ ")
        print(f"{m.id:>6} {m.date.astimezone():%d.%m %H:%M:%S} {sender:>3} {sysmsg:<6} {markup:<6} | {body[:160]}")
    await client.disconnect()


asyncio.run(main())
