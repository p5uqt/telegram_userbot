#!/usr/bin/env bash
# Запуск userbot с автоперезапуском.
#
# Зачем: Telethon не имеет таймаута на запрос. Если TCP-соединение повисло
# полумёртвым (Wi-Fi моргнул, ноут уходил в сон), бот живёт, но не получает
# ответов и молчит до ручного перезапуска. Watchdog в userbot.py это ловит и
# выходит с кодом 3 — этот скрипт поднимает процесс заново.
#
# В терминале: бот работает в фоне (лог — в state/userbot.log), а на экране — ub
# (help — команды, logs — посмотреть лог, exit — остановить всё).
# Без терминала (nohup, cron, ./run.sh > file) — как раньше: лог прямо в вывод.
cd "$(dirname "$0")" || exit 1
mkdir -p state
LOG=state/userbot.log
export PYTHONUNBUFFERED=1   # чтобы лог в файле появлялся сразу, а не пачками

bot_loop() {
    while true; do
        .venv/bin/python userbot.py
        code=$?
        if [ "$code" -eq 75 ]; then   # команда restart из ub — сразу
            echo "[run] перезапуск по команде restart" >&2
            continue
        fi
        echo "[run] userbot завершился (код $code), перезапуск через 5 с..." >&2
        sleep 5
    done
}

if [ ! -t 0 ] || [ ! -t 1 ] || [ "$1" = "--log" ]; then
    bot_loop   # старый режим: лог прямо в терминал
    exit
fi

# каждый запуск — новый лог; предыдущий остаётся в userbot.log.1 (на случай «что было до перезапуска»)
[ -f "$LOG" ] && mv -f "$LOG" "$LOG.1"
echo "[run] старт $(date '+%d.%m %H:%M:%S')" > "$LOG"
bot_loop >> "$LOG" 2>&1 &
BOT=$!
stop() {
    pkill -TERM -P "$BOT" 2>/dev/null   # сам userbot.py
    kill "$BOT" 2>/dev/null             # и цикл перезапуска
    wait "$BOT" 2>/dev/null
}
trap stop EXIT
trap 'exit 143' TERM HUP
trap ':' INT   # Ctrl+C — для ub (стереть строку / выйти из logs), а не остановка всего

.venv/bin/python ub.py --main
echo "бот остановлен"
