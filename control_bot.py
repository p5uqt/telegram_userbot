"""Бот управления: полный доступ к userbot из обычного Telegram-бота (необязательно).

Включается токеном CONTROL_BOT_TOKEN в .env (бота создаёшь у @BotFather). Бот — это ещё один ub:
он подключается к control.sock аккаунтов, как ./ub, поэтому умеет всё то же самое — status, chats,
open (переписка вживую), tell, write, send, undo, set, approve, restart… — плюс accounts / use / all
для нескольких аккаунтов. Черновики (approve) приходят с кнопками, уведомления — по CONTROL_BOT_NOTIFY.

Слушается только админов: CONTROL_BOT_ADMINS (id или @ник), по умолчанию — владельцы аккаунтов
userbot. Всем остальным бот молчит, а попытка пишется в лог и тебе в уведомления.

Несколько аккаунтов: бота держит один процесс userbot (файловая блокировка в корневом state/),
остальные ждут и подхватывают его, если тот процесс остановится.
"""
import asyncio
import fcntl
import hashlib
import json
import time

from telethon import Button, TelegramClient, events
from telethon.tl import functions, types

import accounts

CHUNK = 3900          # Telegram режет сообщения на 4096 символах
LOCAL_HELP = (
    "Бот управления userbot. Пиши команды как в ub — без точки и без .ub:\n"
    "  status · chats · open 3 · tell @masha … · write … · undo · drafts · restart …\n"
    "Можно и через «/»: /status, /chats, /drafts.\n\n"
    "Команды самого бота:\n"
    "  accounts        аккаунты: какие запущены, какой выбран\n"
    "  use <имя>       работать с аккаунтом (если их несколько)\n"
    "  all <команда>   на всех запущенных аккаунтах: all pause, all status\n"
    "  logs [n]        последние n строк лога аккаунта (по умолчанию 30)\n\n"
    "open <кто> — переписка этого чата будет приходить сюда вживую; close — перестать.\n"
    "Черновики приходят с кнопками; ответь на карточку своим текстом — он уйдёт вместо черновика.")
MENU = [("status", "состояние бота"), ("chats", "последние чаты"), ("drafts", "черновики"),
        ("accounts", "аккаунты"), ("help", "справка")]
_ALL_SUFFIX = {"restart", "pause", "resume", "status", "media"}
_DRAFT_OK = {"+", "ok", "ок", "да", "го", "отправь", "отправить", "👍", "yes", "y"}
_DRAFT_FORCE = {"ok!", "ок!", "+!"}
_DRAFT_NO = {"-", "no", "нет", "не надо", "отмена", "не отправляй", "cancel", "👎", "n"}


def log(*args) -> None:
    print("[бот управления]", *args, flush=True)


def chunks(text: str) -> list[str]:
    """Длинный ответ (history, help) — на несколько сообщений, по границам строк."""
    out, cur = [], ""
    for line in (text or "(пусто)").split("\n"):
        while len(line) > CHUNK:
            if cur:
                out.append(cur)
                cur = ""
            out.append(line[:CHUNK])
            line = line[CHUNK:]
        if cur and len(cur) + len(line) + 1 > CHUNK:
            out.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur.strip():
        out.append(cur)
    return out or ["(пусто)"]


async def oneshot(account: str, line: str, timeout: float = 180) -> str:
    """Одна команда аккаунту по отдельному соединению (как ./ub -a <имя> <команда>)."""
    try:
        reader, writer = await asyncio.open_unix_connection(str(accounts.control_sock(account)))
    except OSError:
        return f"{account} не запущен"
    try:
        writer.write((json.dumps({"line": line}, ensure_ascii=False) + "\n").encode())
        await writer.drain()
        async with asyncio.timeout(timeout):
            while raw := await reader.readline():
                try:
                    obj = json.loads(raw)
                except ValueError:
                    continue
                if obj.get("type") == "result":
                    return obj.get("text", "")
        return f"{account}: соединение оборвалось"
    except TimeoutError:
        return f"{account} не ответил за {int(timeout)} с"
    except OSError as exc:
        return f"{account}: ошибка связи ({exc})"
    finally:
        writer.close()


async def running() -> list[str]:
    out = []
    for name in accounts.list_accounts():
        try:
            _, w = await asyncio.open_unix_connection(str(accounts.control_sock(name)))
            w.close()
            out.append(name)
        except OSError:
            pass
    return out


class Link:
    """Постоянное соединение с control.sock одного аккаунта — как у ub: команды по очереди,
    живые сообщения открытого чата — в on_msg. После перезапуска аккаунта подключается заново
    и снова открывает чат, который был открыт."""

    def __init__(self, account: str, on_msg, subscribe: bool = False, announce: bool = False):
        self.account, self.on_msg, self.subscribe, self.announce = account, on_msg, subscribe, announce
        self.reader = self.writer = None
        self.connected = False
        self.results: asyncio.Queue = asyncio.Queue()
        self.lock = asyncio.Lock()
        self.skip = 0
        self.chat: str | None = None
        self.chat_id: int | None = None
        self.closed = False
        self.task: asyncio.Task | None = None

    def _write(self, obj: dict) -> None:
        self.writer.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())

    async def _connect(self) -> bool:
        try:
            self.reader, self.writer = await asyncio.open_unix_connection(str(accounts.control_sock(self.account)))
        except OSError:
            return False
        if self.subscribe:
            self._write({"subscribe": ["notify"]})   # уведомления и итоги черновиков — только этому соединению
        if self.chat_id:
            self.skip += 1
            self._write({"line": f"open {self.chat_id}"})
        self.connected = True
        return True

    async def start(self) -> bool:
        ok = await self._connect()
        self.task = asyncio.create_task(self._loop(ok))
        return ok

    async def _loop(self, connected: bool) -> None:
        lost_at = None
        while not self.closed:
            if not connected:
                await asyncio.sleep(3)
                connected = await self._connect()
                if connected and lost_at and self.announce:
                    await self._say("снова на связи" + (f", чат {self.chat} открыт" if self.chat else ""))
                    lost_at = None
                continue
            try:
                while raw := await self.reader.readline():
                    try:
                        obj = json.loads(raw)
                    except ValueError:
                        continue
                    if obj.get("type") == "result":
                        if self.skip:
                            self.skip -= 1
                            continue
                        self.chat, self.chat_id = obj.get("chat"), obj.get("chat_id")
                        self.results.put_nowait(obj.get("text", ""))
                    elif obj.get("type") == "msg":
                        try:
                            await self.on_msg(self.account, obj)
                        except Exception as exc:  # noqa: BLE001
                            log(f"не переслал сообщение {self.account}: {exc}")
            except (OSError, asyncio.IncompleteReadError):
                pass
            if self.closed:
                return
            connected, self.connected, self.skip = False, False, 0
            if self.lock.locked():
                self.results.put_nowait(f"{self.account}: соединение оборвалось (перезапускается?) — "
                                        "повтори через пару секунд")
            if self.announce and not lost_at:
                lost_at = time.time()
                await self._say("перезапускается — переподключаюсь…")

    async def _say(self, text: str) -> None:
        try:
            await self.on_msg(self.account, {"type": "msg", "kind": "sys", "text": text})
        except Exception:  # noqa: BLE001
            pass

    async def request(self, line: str, timeout: float = 180) -> str:
        async with self.lock:
            for _ in range(20):          # аккаунт перезапускается — подождём до 10 с
                if self.connected:
                    break
                await asyncio.sleep(0.5)
            if not self.connected:
                return f"{self.account} сейчас недоступен (не запущен или перезапускается)"
            while not self.results.empty():
                self.results.get_nowait()
            try:
                self._write({"line": line})
                await self.writer.drain()
            except (OSError, AttributeError):
                return f"{self.account} сейчас недоступен"
            try:
                return await asyncio.wait_for(self.results.get(), timeout)
            except asyncio.TimeoutError:
                return f"{self.account} не ответил за {int(timeout)} с"

    async def close(self) -> None:
        self.closed = True
        if self.task:
            self.task.cancel()
        if self.writer:
            self.writer.close()


class ControlBot:
    def __init__(self, token: str, api_id: int, api_hash: str, admins: list[str], notify_level: str,
                 own_account: str, owner_notify):
        self.token, self.api_id, self.api_hash = token, api_id, api_hash
        self.admins_cfg = [a.strip() for a in admins if a.strip()]
        self.notify_level = notify_level
        self.own = own_account
        self.owner_notify = owner_notify          # уведомление в userbot (о чужих попытках)
        self.tag = hashlib.sha1(token.encode()).hexdigest()[:10]
        self.bot: TelegramClient | None = None
        self.sessions: dict[int, dict] = {}       # admin id → {"account", "link"}
        self.monitor: dict[str, Link] = {}        # аккаунт → соединение для черновиков/уведомлений
        self.cards: dict[int, tuple[str, int, int, str]] = {}   # id сообщения → (аккаунт, №, админ, текст)
        self.strangers: set[int] = set()
        self._admins_cache: tuple[float, set[int], set[str]] = (0.0, set(), set())

    # ── кто админ ───────────────────────────────────────────────────────────
    def admins(self) -> tuple[set[int], set[str]]:
        """CONTROL_BOT_ADMINS (id и @ники); пусто — владельцы всех аккаунтов (state/me.json)."""
        if time.time() - self._admins_cache[0] < 60:
            return self._admins_cache[1], self._admins_cache[2]
        ids, names = set(), set()
        for a in self.admins_cfg:
            if a.lstrip("-").isdigit():
                ids.add(int(a))
            else:
                names.add(a.lstrip("@").lower())
        if not self.admins_cfg:
            for acc in accounts.list_accounts():
                try:
                    ids.add(int(json.loads((accounts.state_dir(acc) / "me.json").read_text())["id"]))
                except (OSError, ValueError, KeyError, TypeError):
                    pass
        self._admins_cache = (time.time(), ids, names)
        return ids, names

    def is_admin(self, user) -> bool:
        ids, names = self.admins()
        return bool(user) and (user.id in ids or (getattr(user, "username", None) or "").lower() in names)

    async def check(self, event) -> bool:
        sender = await event.get_sender()
        if self.is_admin(sender):
            return True
        uid = getattr(sender, "id", 0)
        if uid not in self.strangers:   # один раз на человека: и в лог, и тебе
            self.strangers.add(uid)
            who = f"id {uid}" + (f" (@{sender.username})" if getattr(sender, "username", None) else "")
            log(f"чужой пишет боту управления: {who} — не отвечаю. Если это ты — добавь {uid} в CONTROL_BOT_ADMINS")
            await self.owner_notify(f"🛡 боту управления пишет не админ: {who}. Ему ничего не ответил. "
                                    f"Если это ты — CONTROL_BOT_ADMINS={uid} в .env", important=True)
        return False

    # ── отправка админу ────────────────────────────────────────────────────
    async def send(self, chat_id: int, text: str, buttons=None) -> list:
        sent = []
        parts = chunks(text)
        for i, part in enumerate(parts):
            try:
                sent.append(await self.bot.send_message(chat_id, part,
                                                        buttons=buttons if i == len(parts) - 1 else None))
            except Exception as exc:  # noqa: BLE001 — админ ещё не нажал /start, заблокировал бота…
                log(f"не смог написать {chat_id}: {exc}")
                break
        return sent

    async def to_admins(self, text: str, buttons=None) -> list:
        ids, _ = self.admins()
        targets = ids | set(self.sessions)
        out = []
        for uid in targets:
            for m in await self.send(uid, text, buttons):
                out.append((uid, m))
        return out

    def multi(self) -> bool:
        return len(accounts.list_accounts()) > 1

    def tag_acc(self, account: str) -> str:
        return f"[{account}] " if self.multi() else ""

    # ── сессия админа: выбранный аккаунт и его соединение ──────────────────
    async def session(self, admin: int) -> dict:
        s = self.sessions.get(admin)
        if s is None:
            on = await running()
            names = accounts.list_accounts()
            default = self.own if self.own in on else (on[0] if on else (names[0] if names else self.own))
            s = self.sessions[admin] = {"account": None, "link": None}
            await self.use(admin, default)
        return s

    async def use(self, admin: int, account: str) -> str:
        s = self.sessions.setdefault(admin, {"account": None, "link": None})
        if s["link"]:
            await s["link"].close()

        async def live(acc: str, obj: dict, admin=admin) -> None:
            if obj.get("kind") in ("draft", "notify", "draft_done"):
                return   # это приходит через монитор, всем админам
            await self.send(admin, self.tag_acc(acc) + obj.get("text", ""))

        link = Link(account, live, announce=True)
        s["account"], s["link"] = account, link
        ok = await link.start()
        return f"аккаунт {account}" + ("" if ok else " (сейчас не запущен — подключусь, когда поднимется)")

    async def ask(self, admin: int, line: str) -> str:
        s = await self.session(admin)
        return await s["link"].request(line)

    # ── монитор: черновики и уведомления со всех аккаунтов ─────────────────
    async def monitor_loop(self) -> None:
        while True:
            for acc in await running():
                if acc not in self.monitor:
                    link = Link(acc, self.on_monitor, subscribe=True)
                    if await link.start():
                        self.monitor[acc] = link
                    else:
                        await link.close()
            await asyncio.sleep(20)

    async def on_monitor(self, acc: str, obj: dict) -> None:
        kind = obj.get("kind")
        if kind == "draft":
            no = int(obj.get("no", 0))
            text = self.tag_acc(acc) + (obj.get("card") or obj.get("text", ""))
            buttons = [[Button.inline("✅ Отправить", f"d|{acc}|ok|{no}".encode()),
                        Button.inline("🔁 Переписать", f"d|{acc}|redo|{no}".encode())],
                       [Button.inline("❌ Не отправлять", f"d|{acc}|no|{no}".encode())]]
            for uid, m in await self.to_admins(text, buttons):
                self.cards[m.id] = (acc, no, uid, text)
            while len(self.cards) > 300:
                self.cards.pop(next(iter(self.cards)))
        elif kind == "draft_done":
            no, status = int(obj.get("no", 0)), obj.get("status", "")
            for mid, (a, n, uid, text) in list(self.cards.items()):
                if a == acc and n == no:
                    try:
                        await self.bot.edit_message(uid, mid, f"{text}\n\n— {status}"[:4000], buttons=None)
                    except Exception:  # noqa: BLE001 — сообщение могли удалить
                        pass
                    self.cards.pop(mid, None)
        elif kind == "notify":
            if self.notify_level == "off" or (self.notify_level == "important" and not obj.get("important")):
                return
            await self.to_admins(self.tag_acc(acc) + obj.get("text", ""))

    # ── команды ────────────────────────────────────────────────────────────
    async def handle_line(self, admin: int, line: str) -> str:
        parts = line.split()
        cmd = parts[0].lower()
        if cmd in _ALL_SUFFIX and any(x.lower() == "all" for x in parts[1:]):
            parts = ["all", cmd] + [x for x in parts[1:] if x.lower() != "all"]   # restart all = all restart
            cmd = "all"
        elif cmd == "all" and len(parts) > 1 and parts[1].lower() == "logs":
            parts, cmd = ["logs"] + parts[2:], "logs"   # all logs — в боте лог одного аккаунта
        if cmd in ("start", "help", "h", "?") and len(parts) == 1:
            return LOCAL_HELP + "\n\n" + await self.ask(admin, "help")
        if cmd == "start":
            return LOCAL_HELP
        if cmd == "accounts":
            on, cur = set(await running()), (await self.session(admin))["account"]
            rows = [f"{'●' if n in on else '○'} {n}{'' if n in on else '  (не запущен)'}"
                    f"{'  ← выбран' if n == cur else ''}" for n in accounts.list_accounts()]
            return "\n".join(rows) or "аккаунтов нет"
        if cmd == "use":
            if len(parts) < 2:
                return "use <имя> — accounts покажет список"
            if parts[1] not in accounts.list_accounts():
                return f"нет аккаунта «{parts[1]}» — accounts"
            return await self.use(admin, parts[1])
        if cmd == "all":
            rest = " ".join(parts[1:])
            if not rest:
                return "all <команда>, например all pause"
            on = await running()
            if not on:
                return "ни один аккаунт не запущен"
            res = await asyncio.gather(*(oneshot(n, rest) for n in on))
            return "\n\n".join(f"── {n} ──\n{r}" for n, r in zip(on, res))
        if cmd == "logs":
            n = next((int(x) for x in parts[1:] if x.isdigit()), 30)
            acc = (await self.session(admin))["account"]
            path = accounts.state_dir(acc) / "userbot.log"
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    tail = fh.readlines()[-min(n, 300):]
            except OSError:
                return f"лога нет ({path.name}) — бот запущен не через ./run.sh? (под systemd — journalctl)"
            return f"── лог {acc}, последние {len(tail)} строк ──\n" + "".join(tail).rstrip()
        if cmd in ("exit", "quit", "q", "clear"):
            return "в боте это не нужно: просто закрой чат. Остановить автоответы — pause"
        return self.tag_acc((await self.session(admin))["account"]) + await self.ask(admin, line)

    @staticmethod
    def draft_line(no: int, text: str) -> str:
        low = text.strip().lower()
        if low in _DRAFT_OK:
            return f"ok {no}"
        if low in _DRAFT_FORCE:
            return f"ok! {no}"
        if low in _DRAFT_NO:
            return f"no {no}"
        first, _, rest = text.strip().partition(" ")
        if first.lower() in ("redo", "заново", "переделай", "перепиши"):
            return f"redo {no} {rest}".strip()
        return f"edit {no} {text.strip()}"

    async def on_message(self, event) -> None:
        if not await self.check(event):
            return
        text = (event.raw_text or "").strip()
        if not text:
            return
        admin = event.sender_id
        card = self.cards.get(event.message.reply_to_msg_id or 0)
        if card:   # ответ на карточку черновика: «+», «-», «redo …» или свой текст
            acc, no = card[0], card[1]
            res = await oneshot(acc, self.draft_line(no, text))
            await self.send(admin, self.tag_acc(acc) + res)
            return
        if text.startswith("/"):   # /status, /tell@имябота … → status, tell …
            first, _, rest = text[1:].partition(" ")
            text = (first.split("@", 1)[0] + (" " + rest if rest else "")).strip()
            if not text:
                return
        try:
            async with self.bot.action(admin, "typing"):
                res = await self.handle_line(admin, text)
        except Exception as exc:  # noqa: BLE001
            res = f"⚠️ {exc}"
        await self.send(admin, res)

    async def on_callback(self, event) -> None:
        if not await self.check(event):
            await event.answer("нет доступа")
            return
        try:
            _, acc, act, no = event.data.decode().split("|")
        except ValueError:
            await event.answer()
            return
        res = await oneshot(acc, f"{act} {no}")
        await event.answer(res[:190])   # кнопку карточки обновит итог черновика (draft_done)

    # ── запуск ─────────────────────────────────────────────────────────────
    async def serve(self) -> None:
        session = accounts.state_dir(accounts.MAIN) / f"control_bot_{self.tag}"
        self.bot = TelegramClient(str(session), self.api_id, self.api_hash)
        self.bot.parse_mode = None   # текст как есть: в выводе команд бывают * _ ` [ ]
        await self.bot.start(bot_token=self.token)
        me = await self.bot.get_me()
        log(f"@{me.username} работает (аккаунт {self.own} держит бота)")
        try:
            await self.bot(functions.bots.SetBotCommandsRequest(
                scope=types.BotCommandScopeDefault(), lang_code="",
                commands=[types.BotCommand(c, d) for c, d in MENU]))
        except Exception as exc:  # noqa: BLE001
            log(f"меню команд не задал: {exc}")
        self.bot.add_event_handler(self.on_message, events.NewMessage(incoming=True, func=lambda e: e.is_private))
        self.bot.add_event_handler(self.on_callback, events.CallbackQuery())
        mon = asyncio.create_task(self.monitor_loop())
        try:
            await self.bot.run_until_disconnected()
        finally:
            mon.cancel()
            for link in list(self.monitor.values()) + [s["link"] for s in self.sessions.values() if s["link"]]:
                await link.close()
            self.monitor.clear()
            self.sessions.clear()

    async def run(self) -> None:
        """Бота держит один процесс: кто взял блокировку, тот и запускает; остальные ждут."""
        lock_path = accounts.state_dir(accounts.MAIN) / f"control_bot_{self.tag}.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        waiting_said = False
        while True:
            fh = open(lock_path, "w")
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                fh.close()
                if not waiting_said:
                    log("бота держит другой аккаунт — подхвачу, если тот остановится")
                    waiting_said = True
                await asyncio.sleep(30)
                continue
            try:
                await self.serve()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                name = type(exc).__name__
                if "Token" in name or "token" in str(exc).lower():
                    log(f"токен не подходит ({name}: {exc}) — проверь CONTROL_BOT_TOKEN, бот выключен")
                    fh.close()
                    return
                log(f"упал: {name}: {exc} — перезапуск через 30 с")
            finally:
                if self.bot:
                    try:
                        await self.bot.disconnect()
                    except Exception:  # noqa: BLE001
                        pass
            fh.close()
            await asyncio.sleep(30)
