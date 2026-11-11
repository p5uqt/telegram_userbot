#!/usr/bin/env bash
# Запуск userbot с автоперезапуском — всех аккаунтов сразу.
#
# Аккаунты: main (state/ в корне) + каждая папка accounts/<имя>/, где уже выполнен вход
# (login.py -a <имя> ...). На каждый аккаунт — свой процесс, свой лог
# (<папка аккаунта>/state/userbot.log); упал один — остальные работают.
# ./run.sh work home  — запустить только перечисленные аккаунты.
#
# Зачем перезапуск: Telethon не имеет таймаута на запрос. Если TCP-соединение повисло
# полумёртвым (Wi-Fi моргнул, ноут уходил в сон), бот живёт, но не получает
# ответов и молчит до ручного перезапуска. Watchdog в userbot.py это ловит и
# выходит с кодом 3 — этот скрипт поднимает процесс заново.
#
# В терминале: боты работают в фоне, а на экране — ub
# (help — команды, accounts / use <имя> — аккаунты, logs — лог, exit — остановить всё).
# Без терминала (nohup, cron, ./run.sh > file) — лог прямо в вывод, строки с [имя].
cd "$(dirname "$0")" || exit 1
mkdir -p state
export PYTHONUNBUFFERED=1   # чтобы лог в файле появлялся сразу, а не пачками

LOG_MODE=0
NAMES=()
for a in "$@"; do
    if [ "$a" = "--log" ]; then LOG_MODE=1; else NAMES+=("$a"); fi
done
if [ ${#NAMES[@]} -eq 0 ]; then
    mapfile -t NAMES < <(.venv/bin/python -c '
import accounts
for n in accounts.list_accounts():
    if accounts.has_session(n):
        print(n)')
fi
if [ ${#NAMES[@]} -eq 0 ]; then
    echo "нет ни одного аккаунта со входом: сначала ./login.py (или ./login.py -a <имя> ...)" >&2
    exit 1
fi

acc_state() {   # папка state/ аккаунта
    if [ "$1" = main ]; then echo state; else echo "accounts/$1/state"; fi
}

bot_loop() {    # $1 — имя аккаунта
    while true; do
        .venv/bin/python userbot.py --account "$1"
        code=$?
        if [ "$code" -eq 75 ]; then   # команда restart из ub — сразу
            echo "[run:$1] перезапуск по команде restart" >&2
            continue
        fi
        echo "[run:$1] userbot завершился (код $code), перезапуск через 5 с..." >&2
        sleep 5
    done
}

PIDS=()
stop() {
    for p in "${PIDS[@]}"; do
        pkill -TERM -P "$p" 2>/dev/null   # сам userbot.py
        kill "$p" 2>/dev/null             # и цикл перезапуска
    done
    for p in "${PIDS[@]}"; do wait "$p" 2>/dev/null; done
}
trap stop EXIT
trap 'exit 143' TERM HUP

if [ ! -t 0 ] || [ ! -t 1 ] || [ "$LOG_MODE" = 1 ]; then
    # старый режим: лог прямо в терминал; при нескольких аккаунтах строки помечены [имя]
    for n in "${NAMES[@]}"; do
        if [ ${#NAMES[@]} -eq 1 ]; then
            bot_loop "$n" &
        else
            bot_loop "$n" > >(sed -u "s/^/[$n] /") 2>&1 &
        fi
        PIDS+=($!)
    done
    wait
    exit
fi

for n in "${NAMES[@]}"; do
    st=$(acc_state "$n")
    mkdir -p "$st"
    LOG="$st/userbot.log"
    # каждый запуск — новый лог; предыдущий остаётся в userbot.log.1 (на случай «что было до перезапуска»)
    [ -f "$LOG" ] && mv -f "$LOG" "$LOG.1"
    echo "[run] старт $(date '+%d.%m %H:%M:%S')" > "$LOG"
    bot_loop "$n" >> "$LOG" 2>&1 &
    PIDS+=($!)
done
echo "запущены аккаунты: ${NAMES[*]}"
trap ':' INT   # Ctrl+C — для ub (стереть строку / выйти из logs), а не остановка всего

.venv/bin/python ub.py --main   # несколько аккаунтов — общий режим ub>, один — сразу он
echo "боты остановлены"
