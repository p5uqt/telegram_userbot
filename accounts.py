"""Несколько Telegram-аккаунтов: где лежат файлы каждого.

main  — основной аккаунт: .env и state/ в корне (как было всегда).
<имя> — дополнительный: accounts/<имя>/.env (только отличия от корневого .env)
        и accounts/<имя>/state/ (сессия, память о собеседниках, лог, сокет ub).
Личность (persona.md, personality.toml), media/ и files/ — общие для всех.

Аккаунт выбирается флагом --account <имя> (или -a <имя>) у любого скрипта:
    login.py -a work +380...      qr_login.py -a work      userbot.py -a work
"""
import hashlib
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ACCOUNTS_DIR = HERE / "accounts"
MAIN = "main"
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def pop_account_arg(argv: list[str]) -> str:
    """Достаёт --account/-a <имя> из argv (на месте), чтобы скрипты дальше видели свои аргументы как раньше."""
    name = os.environ.get("UB_ACCOUNT", "").strip() or MAIN
    for i, a in enumerate(argv[1:], 1):
        if a in ("--account", "-a") and i + 1 < len(argv):
            name = argv[i + 1]
            del argv[i:i + 2]
            break
        if a.startswith("--account="):
            name = a.split("=", 1)[1]
            del argv[i]
            break
    if not NAME_RE.match(name):
        sys.exit(f"плохое имя аккаунта «{name}»: латиница, цифры, _ и -")
    return name


def account_dir(name: str) -> Path:
    return HERE if name == MAIN else ACCOUNTS_DIR / name


def state_dir(name: str) -> Path:
    return account_dir(name) / "state"


def control_sock(name: str) -> Path:
    """У unix-сокета предел длины пути ~107 байт; если путь длиннее — сокет в /run/user."""
    p = state_dir(name) / "control.sock"
    if len(str(p).encode()) <= 100:
        return p
    run = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/ub-{os.getuid()}")
    run.mkdir(mode=0o700, exist_ok=True)
    tag = hashlib.sha1(str(HERE).encode()).hexdigest()[:8]
    return run / f"ub-{tag}-{name}.sock"


def list_accounts() -> list[str]:
    """main (если в нём уже есть сессия или нет других) + все папки accounts/<имя>/."""
    extra = sorted(d.name for d in ACCOUNTS_DIR.iterdir()
                   if d.is_dir() and NAME_RE.match(d.name) and d.name != MAIN) if ACCOUNTS_DIR.is_dir() else []
    main_on = (state_dir(MAIN) / "account.session").exists() or not extra
    return ([MAIN] if main_on else []) + extra


def has_session(name: str) -> bool:
    return (state_dir(name) / "account.session").exists()
