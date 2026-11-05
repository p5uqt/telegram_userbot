#!/usr/bin/env python3
"""Non-interactive login in steps:
  login.py +380XXXXXXXXX        -> Telegram sends a code
  login.py code 12345           -> sign in
  login.py password <2FA pass>  -> only if two-step verification is on
"""
import asyncio
import json
import sys

from telethon import TelegramClient
from telethon.errors import PasswordHashInvalidError, SessionPasswordNeededError

import userbot as u

PENDING = u.HERE / "state" / "login.json"


async def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    (u.HERE / "state").mkdir(exist_ok=True)
    client = TelegramClient(str(u.HERE / "state" / "account"), u.CFG["api_id"], u.CFG["api_hash"])
    await client.connect()
    try:
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"уже вошёл как {me.first_name} (@{me.username})")
            return
        if args[0] == "code":
            pending = json.loads(PENDING.read_text())
            try:
                await client.sign_in(pending["phone"], args[1], phone_code_hash=pending["hash"])
            except SessionPasswordNeededError:
                print("включена двухфакторка: выполни  login.py password <облачный пароль>")
                return
        elif args[0] == "password":
            try:
                await client.sign_in(password=" ".join(args[1:]))
            except PasswordHashInvalidError:
                print("неверный облачный пароль, попробуй ещё раз")
                return
        else:
            sent = await client.send_code_request(args[0])
            PENDING.write_text(json.dumps({"phone": args[0], "hash": sent.phone_code_hash}))
            print("код отправлен в Telegram. выполни:  login.py code <код>")
            return
        me = await client.get_me()
        PENDING.unlink(missing_ok=True)
        print(f"готово, вошёл как {me.first_name} (@{me.username})")
    finally:
        await client.disconnect()


asyncio.run(main())
