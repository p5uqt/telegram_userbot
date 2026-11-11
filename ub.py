#!/usr/bin/env python3
"""ub — управление userbot.

./run.sh   запускает бота в фоне и сразу открывает ub (exit — остановить бота).
./ub       подключиться к уже запущенному боту из другого терминала (exit — только выйти).
./ub status   одна команда и выход.
./ub -a work  работать с аккаунтом work (без -a — первый запущенный).
В ub: accounts — список аккаунтов, use <имя> — переключиться, all <команда> — на всех.
"""
import json
import re
import socket
import sys
import threading
import time
from pathlib import Path

import accounts

HERE = Path(__file__).resolve().parent
MAIN = "--main" in sys.argv          # запущен из run.sh: exit останавливает бота
_ASKED = "--account" in sys.argv or "-a" in sys.argv or any(a.startswith("--account=") for a in sys.argv)
ACCOUNT = accounts.pop_account_arg(sys.argv)
ARGS = [a for a in sys.argv[1:] if a != "--main"]


def sock_path(name: str) -> Path:
    return accounts.control_sock(name)


def log_path(name: str) -> Path:
    return accounts.state_dir(name) / "userbot.log"


def SOCK() -> Path:  # noqa: N802 — текущий аккаунт меняется командой use
    return sock_path(state["account"] or accounts.MAIN)


def LOG() -> Path:  # noqa: N802
    return log_path(state["account"] or accounts.MAIN)


def multi() -> bool:
    return len(accounts.list_accounts()) > 1


GENERAL_CMDS = ["help", "accounts", "use", "all", "logs", "clear", "exit"]
TTY = sys.stdout.isatty()
C = {"in": "\033[36m", "bot": "\033[32m", "me": "\033[33m", "sys": "\033[2m", "log": "\033[2m",
     "err": "\033[31m", "off": "\033[0m"} if TTY else dict.fromkeys(
    ("in", "bot", "me", "sys", "log", "err", "off"), "")
LOCAL_HELP = (
    "\n\nВ ub:\n"
    "  accounts                     аккаунты: какие запущены, кто текущий\n"
    "  use <имя>                    перейти в аккаунт (ub[имя]>); use без имени — назад в общий режим (ub>)\n"
    "  all <команда>                выполнить на всех запущенных аккаунтах (all pause, all status)\n"
    "  logs [n]                     лог вживую (последние n строк + новые), Ctrl+C — назад:\n"
    "                               в общем режиме — всех аккаунтов (строки с [имя]), в аккаунте — только его\n"
    "  logs all [n]                 логи всех аккаунтов, даже если ты в каком-то аккаунте\n"
    "  clear                        очистить экран\n"
    + ("  exit                         остановить бота и выйти (Ctrl+D — то же)\n" if MAIN else
       "  exit                         выйти из ub, бот продолжит работать (Ctrl+D — то же)\n")
    + "↑/↓ — история команд, Tab — дополнение, Ctrl+C — стереть строку, "
      "а в открытом чате с пустой строкой — закрыть чат (как close)")

state = {"chat": None, "chat_id": None, "reading": False, "commands": ["help"], "sock": None,
         "skip": 0, "quit": False, "account": ACCOUNT, "switching": False}
result_ready = threading.Event()
result_text: list[str] = []
print_lock = threading.Lock()


PROMPT_COLOR = "\033[35m" if TTY else ""   # пурпурный — не путается с сообщениями


def prompt(rl: bool = False) -> str:
    """rl=True — для input(): readline'у нужны \\001…\\002 вокруг escape-кодов, иначе ломается длина строки."""
    acc = f"{state['account']}" if state["account"] and multi() else ""
    where = "/".join(x for x in (acc, state["chat"] or "") if x)
    text = f"ub[{where}]> " if where else "ub> "
    if not PROMPT_COLOR:
        return text
    on, off = (f"\001{PROMPT_COLOR}\002", f"\001{C['off']}\002") if rl else (PROMPT_COLOR, C["off"])
    return on + text + off


def show(text: str) -> None:
    """Печать над строкой ввода, не ломая то, что ты набираешь."""
    with print_lock:
        if state["reading"] and TTY:
            import readline
            sys.stdout.write("\r\033[K" + text + "\n" + prompt() + readline.get_line_buffer())
        else:
            sys.stdout.write(text + "\n")
        sys.stdout.flush()


def try_connect(name: str) -> socket.socket | None:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(str(sock_path(name)))
        return s
    except OSError:
        s.close()
        return None


def running() -> list[str]:
    out = []
    for name in accounts.list_accounts():
        s = try_connect(name)
        if s:
            s.close()
            out.append(name)
    return out


def oneshot(name: str, line: str, timeout: float = 60) -> str:
    """Одна команда другому аккаунту по отдельному соединению (для all)."""
    s = try_connect(name)
    if not s:
        return "не запущен"
    try:
        s.settimeout(timeout)
        s.sendall((json.dumps({"line": line}, ensure_ascii=False) + "\n").encode())
        for raw in s.makefile("r", encoding="utf-8"):
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("type") == "result":
                return msg.get("text", "")
        return "соединение оборвалось"
    except OSError as exc:
        return f"ошибка: {exc}"
    finally:
        s.close()


def connect(wait: float, quiet: bool = False) -> socket.socket | None:
    """Подключиться к боту; wait — сколько секунд ждать, пока он поднимется."""
    deadline, said = time.time() + wait, False
    while True:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.connect(str(SOCK()))
            return s
        except OSError:
            s.close()
        if time.time() >= deadline or state["quit"]:
            return None
        if not said and wait > 3 and not quiet:
            print(f"{C['sys']}жду, пока бот запустится… (logs — посмотреть, что он пишет){C['off']}")
            said = True
        time.sleep(0.5)


def send(line: str) -> None:
    state["sock"].sendall((json.dumps({"line": line}, ensure_ascii=False) + "\n").encode())


def handle(raw: str) -> None:
    try:
        msg = json.loads(raw)
    except ValueError:
        return
    kind = msg.get("type")
    if kind == "hello":
        state["commands"] = msg.get("commands", []) + ["logs", "clear", "exit", "accounts", "use", "all"]
    elif kind == "result":
        if state["skip"]:  # ответ на служебный open после переподключения
            state["skip"] -= 1
            return
        state["chat"], state["chat_id"] = msg.get("chat"), msg.get("chat_id")
        result_text[:] = [msg.get("text", "")]
        result_ready.set()
    elif kind == "msg":
        show(C.get(msg.get("kind"), "") + msg.get("text", "") + C["off"])


def reader() -> None:
    while not state["quit"]:
        sock = state["sock"]
        if sock is None:  # общий режим — ни к какому аккаунту не подключены
            time.sleep(0.2)
            continue
        try:
            for raw in sock.makefile("r", encoding="utf-8"):
                handle(raw)
        except OSError:
            pass  # бот упал посреди соединения — как обычный обрыв
        if state["quit"]:
            return
        if state["switching"]:  # use: новый сокет (или None) уже в state["sock"]
            state["switching"] = False
            continue
        # бот перезапускается (watchdog / run.sh) — ждём и подключаемся заново
        acc = state["account"]
        state["skip"] = 0
        result_text[:] = ["соединение с ботом потеряно"]
        result_ready.set()
        show(C["err"] + f"бот {acc} перезапускается — переподключаюсь…" + C["off"])
        s = None
        deadline, warned = time.time() + 120, False
        while not state["quit"] and not state["switching"] and state["account"] == acc:
            s = try_connect(acc)
            if s:
                break
            if not warned and time.time() > deadline:
                show(C["err"] + f"бот {acc} так и не поднялся (logs — посмотреть почему)" + C["off"])
                warned = True
            time.sleep(0.5)
        if state["quit"]:
            return
        if not s:  # пока ждали, ты перешёл в другой аккаунт / общий режим
            state["switching"] = False
            continue
        state["sock"] = s
        if state["chat_id"]:
            state["skip"] += 1
            send(f"open {state['chat_id']}")
        show(C["sys"] + "снова подключён" + C["off"])


def request(line: str) -> str:
    if state["sock"] is None:
        return "сейчас общий режим — выбери аккаунт: use <имя> (accounts — список) или all <команда>"
    result_ready.clear()
    try:
        send(line)
    except OSError:
        return "бот сейчас недоступен (перезапускается?) — попробуй через пару секунд"
    if not result_ready.wait(180):
        return "бот не ответил за 3 минуты"
    return result_text[0] if result_text else ""


def colorize(text: str) -> str:
    """Подсветка истории чата: ← он, → бот, ✎ ты."""
    out = []
    for ln in text.split("\n"):
        k = "me" if "] ✎ ты:" in ln else "bot" if "] → бот:" in ln else "in" if "] ← " in ln else ""
        out.append(C[k] + ln + C["off"] if k else ln)
    return "\n".join(out)


_TIME_RE = re.compile(r"^(\d\d)\.(\d\d) (\d\d:\d\d:\d\d) ")


def _time_key(line: str) -> tuple:
    """«11.11 20:07:49 …» → ("11", "11", "20:07:49") для сортировки (месяц, день, время)."""
    m = _TIME_RE.match(line)
    return (m.group(2), m.group(1), m.group(3)) if m else ()


ACC_COLORS = ["\033[36m", "\033[35m", "\033[33m", "\033[34m", "\033[32m", "\033[91m"] if TTY else [""]


class LogView:
    """Красивый вывод строк лога: «20:07:49  cxbond  текст», дата — разделителем при смене дня."""

    def __init__(self, names: list[str]):
        self.many = len(names) > 1
        self.width = max(map(len, names))
        self.color = {n: ACC_COLORS[i % len(ACC_COLORS)] for i, n in enumerate(names)}
        self.day = None

    def __call__(self, name: str, line: str) -> str:
        m = _TIME_RE.match(line)
        out = ""
        if m:
            day = f"{m.group(1)}.{m.group(2)}"
            if day != self.day:
                out += f"{C['sys']}── {day} ──{C['off']}\n"
                self.day = day
            stamp, text = f"{C['sys']}{m.group(3)}{C['off']}", line[m.end():]
        else:
            stamp, text = " " * 8, line   # продолжение многострочной записи / старый лог без времени
        text = text.rstrip("\n")
        kind = "in" if " ← " in text else "bot" if re.search(r"\] → ", text) else ""
        if kind:
            text = C[kind] + text + C["off"]
        acc = f"{self.color[name]}[{name}]{C['off']}{' ' * (self.width - len(name))} " if self.many else ""
        return f"{out}{stamp}  {acc}{text}\n"


def log_mode(n: int, every: bool = False) -> None:
    """Как раньше в ./run.sh: лог бота вживую. every=True — логи всех аккаунтов разом.
    Ctrl+C — обратно в ub."""
    names = accounts.list_accounts() if every else [state["account"]]
    logs = {name: log_path(name) for name in names if log_path(name).exists()}
    if not logs:
        print(f"лога нет ({log_path(state['account'])}) — бот запущен не через ./run.sh?")
        return
    view = LogView(list(logs))
    what = f"логи аккаунтов {', '.join(logs)}" if view.many else f"лог бота {next(iter(logs))}"
    print(f"{C['sys']}── {what}, Ctrl+C — назад в ub ──{C['off']}")
    files = {}
    try:
        backlog = []   # последние n строк каждого лога — вперемешку по времени, как всё и было
        for name, path in logs.items():
            f = open(path, encoding="utf-8", errors="replace")
            files[name] = f
            key = ()
            for line in f.readlines()[-n:]:
                key = _time_key(line) or key   # строка без времени (старый лог) — вслед за предыдущей
                backlog.append((key, len(backlog), name, line))
        for _, _, name, line in sorted(backlog):
            sys.stdout.write(view(name, line))
        sys.stdout.flush()
        while True:
            idle = True
            for name, f in files.items():
                line = f.readline()
                if line:
                    idle = False
                    sys.stdout.write(view(name, line))
                    sys.stdout.flush()
                elif logs[name].exists() and logs[name].stat().st_size < f.tell():  # лог обрезали/сменили
                    f.seek(0)
            if idle:
                time.sleep(0.2)
    except KeyboardInterrupt:
        print(f"\n{C['sys']}── назад в ub ──{C['off']}")
    finally:
        for f in files.values():
            f.close()


def accounts_text() -> str:
    on = set(running())
    rows = []
    for name in accounts.list_accounts():
        mark = "●" if name in on else "○"
        cur = "  ← текущий" if name == state["account"] else ""
        note = "" if name in on else ("  (не запущен)" if accounts.has_session(name)
                                      else f"  (нет входа: ./login.py -a {name} …)")
        rows.append(f"{mark} {name}{note}{cur}")
    return "\n".join(rows) or "аккаунтов нет"


def switch(name: str | None) -> str:
    """Перейти в аккаунт name; None — в общий режим (ни к кому не подключены)."""
    if name == state["account"]:
        return f"уже {name}" if name else "уже общий режим"
    s = None
    if name is not None:
        if name not in accounts.list_accounts():
            return f"нет аккаунта «{name}» — accounts"
        s = try_connect(name)
        if not s:
            return f"{name} не запущен"
    old = state["sock"]
    state["switching"] = old is not None   # reader читает старый сокет — пусть просто перейдёт на новый
    state["account"], state["chat"], state["chat_id"], state["skip"] = name, None, None, 0
    state["sock"] = s
    state["commands"] = GENERAL_CMDS if s is None else state["commands"]
    if old is not None:
        try:
            old.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        old.close()
    return f"теперь аккаунт {name} (logs — его лог; use — назад в общий режим)" if name else \
        "общий режим: logs — все аккаунты, use <имя> — перейти в аккаунт"


def run_all(line: str) -> str:
    on = running()
    if not on:
        return "ни один аккаунт не запущен"
    return "\n\n".join(f"── {name} ──\n{oneshot(name, line)}" for name in on)


def wait_any(wait: float) -> list[str]:
    """Ждём, пока поднимется хоть один аккаунт (из run.sh они стартуют чуть позже ub)."""
    deadline, said = time.time() + wait, False
    while True:
        on = running()
        if on or time.time() >= deadline:
            return on
        if not said and wait > 3:
            print(f"{C['sys']}жду, пока боты запустятся… (logs — посмотреть, что они пишут){C['off']}")
            said = True
        time.sleep(0.5)


def main() -> None:
    general = multi() and not _ASKED and not ARGS   # несколько аккаунтов — стартуем в общем режиме
    if general:
        on = wait_any(90 if MAIN else 0)
        if not on:
            if MAIN:
                print("боты не запустились за 90 с — смотри логи:")
                log_mode(40, every=True)
            sys.exit("боты не запущены: сначала ./run.sh")
        state["account"], state["commands"] = None, GENERAL_CMDS
    else:
        if not _ASKED:  # без -a — первый запущенный аккаунт (обычно main)
            on = running()
            if on and ACCOUNT not in on:
                state["account"] = on[0]
        s = connect(90 if MAIN else 0)
        if not s:
            if MAIN:
                print(f"бот не запустился за 90 с — смотри {LOG()}")
                log_mode(40)
            sys.exit("бот не запущен: сначала ./run.sh")
        state["sock"] = s
    threading.Thread(target=reader, daemon=True).start()

    if ARGS:  # ./ub status — одна команда
        time.sleep(0.2)
        print(colorize(request(" ".join(ARGS))))
        return

    import readline
    hist = accounts.state_dir(accounts.MAIN) / "ub_history"
    try:
        readline.read_history_file(hist)
    except OSError:
        pass
    readline.set_completer(lambda text, i: ([n + " " for n in state["commands"] if n.startswith(text)]
                                            + [None])[i] if readline.get_begidx() == 0 else None)
    readline.parse_and_bind("tab: complete")
    stop = "exit — остановить ботов" if MAIN else "exit — выйти (боты продолжат работать)"
    if general:
        print(f"{C['sys']}работают аккаунты: {', '.join(running())}. use <имя> — перейти в аккаунт, "
              f"logs — общий лог, help — команды, {stop}{C['off']}")
    else:
        print(f"{C['sys']}бот работает. help — команды, logs — лог бота, {stop}{C['off']}")
    while True:
        try:
            state["reading"] = True
            line = input(prompt(rl=True)).strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            # набранное стирается; в открытом чате с пустой строкой Ctrl+C закрывает чат (назад в ub>)
            typed = readline.get_line_buffer().strip()
            print()
            if state["chat"] and not typed:
                state["reading"] = False
                with print_lock:
                    print(f"{C['sys']}{request('close')}{C['off']}")
            continue
        finally:
            state["reading"] = False
        if not line:
            continue
        try:
            readline.write_history_file(hist)
        except OSError:
            pass
        parts = line.split()
        cmd = parts[0].lower()
        if cmd in ("exit", "quit", "q"):
            break
        if cmd == "clear":
            print("\033[2J\033[H", end="")
            continue
        if cmd == "accounts":
            print(accounts_text())
            continue
        if cmd == "use":
            if len(parts) > 1:
                print(switch(parts[1]))
            elif multi():
                print(switch(None))
            else:
                print("аккаунт один — переключаться некуда")
            continue
        if cmd == "all" and len(parts) > 1 and parts[1].lower() == "logs":
            cmd, parts = "logs", ["logs", "all"] + parts[2:]   # all logs = logs all
        if cmd == "all":
            print(colorize(run_all(" ".join(parts[1:]))) if len(parts) > 1 else "all <команда>, например all pause")
            continue
        if cmd == "logs":
            nums = [int(x) for x in parts[1:] if x.isdigit()]
            every = state["account"] is None or any(x.lower() == "all" for x in parts[1:])
            log_mode(nums[0] if nums else 40, every=every)
            continue
        if state["sock"] is None and cmd in ("help", "h", "?"):
            print("общий режим (ub>) — здесь работают:" + LOCAL_HELP.split("В ub:", 1)[1]
                  + "\n\nКоманды бота (status, chats, open, tell, restart…) — внутри аккаунта: use <имя>, "
                    "там help покажет их все. Или сразу всем: all <команда>.")
            continue
        text = request(line)
        if cmd in ("help", "h", "?") and len(parts) == 1:
            text += LOCAL_HELP
        with print_lock:
            print(colorize(text))
    state["quit"] = True
    if MAIN:
        print("останавливаю бота…")


if __name__ == "__main__":
    main()
