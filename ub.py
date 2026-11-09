#!/usr/bin/env python3
"""ub — управление userbot.

./run.sh   запускает бота в фоне и сразу открывает ub (exit — остановить бота).
./ub       подключиться к уже запущенному боту из другого терминала (exit — только выйти).
./ub status   одна команда и выход.
"""
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOCK = HERE / "state" / "control.sock"
LOG = HERE / "state" / "userbot.log"
MAIN = "--main" in sys.argv          # запущен из run.sh: exit останавливает бота
ARGS = [a for a in sys.argv[1:] if a != "--main"]
TTY = sys.stdout.isatty()
C = {"in": "\033[36m", "bot": "\033[32m", "me": "\033[33m", "sys": "\033[2m", "log": "\033[2m",
     "err": "\033[31m", "off": "\033[0m"} if TTY else dict.fromkeys(
    ("in", "bot", "me", "sys", "log", "err", "off"), "")
LOCAL_HELP = (
    "\n\nВ ub:\n"
    "  logs [n]                     режим просмотра лога бота (последние n строк + новые), Ctrl+C — назад\n"
    "  clear                        очистить экран\n"
    + ("  exit                         остановить бота и выйти (Ctrl+D — то же)\n" if MAIN else
       "  exit                         выйти из ub, бот продолжит работать (Ctrl+D — то же)\n")
    + "↑/↓ — история команд, Tab — дополнение, Ctrl+C — стереть строку")

state = {"chat": None, "chat_id": None, "reading": False, "commands": ["help"], "sock": None,
         "skip": 0, "quit": False}
result_ready = threading.Event()
result_text: list[str] = []
print_lock = threading.Lock()


def prompt() -> str:
    return f"ub[{state['chat']}]> " if state["chat"] else "ub> "


def show(text: str) -> None:
    """Печать над строкой ввода, не ломая то, что ты набираешь."""
    with print_lock:
        if state["reading"] and TTY:
            import readline
            sys.stdout.write("\r\033[K" + text + "\n" + prompt() + readline.get_line_buffer())
        else:
            sys.stdout.write(text + "\n")
        sys.stdout.flush()


def connect(wait: float, quiet: bool = False) -> socket.socket | None:
    """Подключиться к боту; wait — сколько секунд ждать, пока он поднимется."""
    deadline, said = time.time() + wait, False
    while True:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.connect(str(SOCK))
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
        state["commands"] = msg.get("commands", []) + ["logs", "clear", "exit"]
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
        try:
            for raw in state["sock"].makefile("r", encoding="utf-8"):
                handle(raw)
        except OSError:
            pass  # бот упал посреди соединения — как обычный обрыв
        if state["quit"]:
            return
        # бот перезапускается (watchdog / run.sh) — ждём и подключаемся заново
        state["skip"] = 0
        result_text[:] = ["соединение с ботом потеряно"]
        result_ready.set()
        show(C["err"] + "бот перезапускается — переподключаюсь…" + C["off"])
        s = connect(120, quiet=True)
        if not s:
            show(C["err"] + "бот так и не поднялся (logs — посмотреть почему)" + C["off"])
            while not state["quit"] and not (s := connect(60, quiet=True)):
                pass
            if not s:
                return
        state["sock"] = s
        if state["chat_id"]:
            state["skip"] += 1
            send(f"open {state['chat_id']}")
        show(C["sys"] + "снова подключён" + C["off"])


def request(line: str) -> str:
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


def log_mode(n: int) -> None:
    """Как раньше в ./run.sh: лог бота вживую. Ctrl+C — обратно в ub."""
    if not LOG.exists():
        print(f"лога нет ({LOG}) — бот запущен не через ./run.sh?")
        return
    print(f"{C['sys']}── лог бота ({LOG.name}), Ctrl+C — назад в ub ──{C['off']}")
    try:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            sys.stdout.write("".join(lines[-n:]))
            sys.stdout.flush()
            while True:
                line = f.readline()
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                else:
                    if LOG.exists() and LOG.stat().st_size < f.tell():  # лог обрезали/сменили
                        f.seek(0)
                    time.sleep(0.2)
    except KeyboardInterrupt:
        print(f"\n{C['sys']}── назад в ub ──{C['off']}")


def main() -> None:
    s = connect(90 if MAIN else 0)
    if not s:
        if MAIN:
            print("бот не запустился за 90 с — смотри state/userbot.log")
            log_mode(40)
        sys.exit("бот не запущен: сначала ./run.sh")
    state["sock"] = s
    threading.Thread(target=reader, daemon=True).start()

    if ARGS:  # ./ub status — одна команда
        time.sleep(0.2)
        print(colorize(request(" ".join(ARGS))))
        return

    import readline
    hist = SOCK.parent / "ub_history"
    try:
        readline.read_history_file(hist)
    except OSError:
        pass
    readline.set_completer(lambda text, i: ([n + " " for n in state["commands"] if n.startswith(text)]
                                            + [None])[i] if readline.get_begidx() == 0 else None)
    readline.parse_and_bind("tab: complete")
    print(f"{C['sys']}бот работает. help — команды, logs — лог бота, "
          f"{'exit — остановить бота' if MAIN else 'exit — выйти (бот продолжит работать)'}{C['off']}")
    while True:
        try:
            state["reading"] = True
            line = input(prompt()).strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()  # как в обычном терминале: Ctrl+C стирает строку, выход — exit / Ctrl+D
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
        if cmd == "logs":
            log_mode(int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 40)
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
