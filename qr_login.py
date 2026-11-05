#!/usr/bin/env python3
"""QR login: scan with Telegram on phone → Settings → Devices → Link Desktop Device.
Writes state/qr.png (opened automatically) and prints the QR in the terminal.
Refreshes the QR every ~25s, gives up after 5 minutes."""
import asyncio
import subprocess
import sys

import qrcode
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

import userbot as u

PNG = u.HERE / "state" / "qr.png"


def show(url: str, first: bool) -> None:
    qrcode.make(url).save(PNG)
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.print_ascii(invert=True)
    print(f"QR обновлён: {PNG}", flush=True)
    if first:
        subprocess.Popen(["xdg-open", str(PNG)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def main() -> None:
    (u.HERE / "state").mkdir(exist_ok=True)
    client = TelegramClient(str(u.HERE / "state" / "account"), u.CFG["api_id"], u.CFG["api_hash"])
    await client.connect()
    try:
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"уже вошёл как {me.first_name} (@{me.username})")
            return
        qr = await client.qr_login()
        show(qr.url, True)
        for _ in range(12):
            try:
                await qr.wait(timeout=25)
                break
            except asyncio.TimeoutError:
                await qr.recreate()
                show(qr.url, False)
            except SessionPasswordNeededError:
                print("QR принят, но включена двухфакторка: выполни  login.py password <облачный пароль>")
                return
        else:
            sys.exit("время вышло, запусти ещё раз")
        me = await client.get_me()
        print(f"готово, вошёл как {me.first_name} (@{me.username})")
    finally:
        PNG.unlink(missing_ok=True)
        await client.disconnect()


asyncio.run(main())
