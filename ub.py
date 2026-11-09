#!/usr/bin/env python3
"""ub — управление запущенным userbot из отдельного терминала.

Бот (./run.sh) должен быть запущен: ub подключается к нему через state/control.sock.
Запуск: ./ub          интерактивно (help — список команд)
        ./ub status   одна команда и выход
"""
import json
import os
import socket
import sys
import threading
from pathlib import Path

SOCK = Path(__file__).resolve().parent / "state" / "control.sock"
TTY = sys.stdout.isatty()
C = {"in": "\033[36m", "bot": "\033[32m", "me": "\033[33m", "sys": "\033[2m", "log": "\033[2m",
     "err": "\033[31m", "off": "\033[0m"} if TTY else dict.fromkeys(
    ("in", "bot", "me", "sys", "log", "err", "off"), "")
LOCAL_HELP = "\n\nВ ub: exit / Ctrl+D — выйти (бот работает дальше), clear — очистить экран, ↑/↓ — история, Tab — дополнение."

state = {"chat": None, "reading": False, "commands": []}
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


def reader(f) -> None:
    for raw in f:
        try:
            msg = json.loads(raw)
        except ValueError:
            continue
        kind = msg.get("type")
        if kind == "hello":
            state["commands"] = msg.get("commands", [])
            result_ready.set()
        elif kind == "result":
            state["chat"] = msg.get("chat")
            result_text[:] = [msg.get("text", "")]
            result_ready.set()
        elif kind == "msg":
            show(C.get(msg.get("kind"), "") + msg.get("text", "") + C["off"])
        elif kind == "log":
            show((C["err"] if msg.get("err") else C["log"]) + msg.get("text", "") + C["off"])
    show(C["err"] + "соединение с ботом закрыто (бот остановлен или перезапускается)" + C["off"])
    os._exit(1)


def request(sock: socket.socket, line: str) -> str:
    result_ready.clear()
    sock.sendall((json.dumps({"line": line}, ensure_ascii=False) + "\n").encode())
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


def main() -> None:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(SOCK))
    except OSError:
        sys.exit("бот не запущен (или старая версия без управления): сначала ./run.sh")
    threading.Thread(target=reader, args=(sock.makefile("r", encoding="utf-8"),), daemon=True).start()
    result_ready.wait(10)

    if len(sys.argv) > 1:  # ./ub status — одна команда
        print(colorize(request(sock, " ".join(sys.argv[1:]))))
        return

    import readline
    hist = SOCK.parent / "ub_history"
    try:
        readline.read_history_file(hist)
    except OSError:
        pass
    names = state["commands"] or ["help"]
    readline.set_completer(lambda text, i: ([n + " " for n in names if n.startswith(text)] + [None])[i]
                           if readline.get_begidx() == 0 else None)
    readline.parse_and_bind("tab: complete")
    print(f"{C['sys']}подключён к боту. help — команды, Ctrl+D — выйти{C['off']}")
    while True:
        try:
            state["reading"] = True
            line = input(prompt()).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        finally:
            state["reading"] = False
        if not line:
            continue
        try:
            readline.write_history_file(hist)
        except OSError:
            pass
        cmd = line.split()[0].lower()
        if cmd in ("exit", "quit", "q"):
            break
        if cmd == "clear":
            print("\033[2J\033[H", end="")
            continue
        text = request(sock, line)
        if cmd in ("help", "h", "?") and len(line.split()) == 1:
            text += LOCAL_HELP
        with print_lock:
            print(colorize(text))


if __name__ == "__main__":
    main()
