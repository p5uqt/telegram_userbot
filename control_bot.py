"""Бот управления: полный доступ к userbot из обычного Telegram-бота (необязательно).

Включается токеном CONTROL_BOT_TOKEN в .env (бота создаёшь у @BotFather). Бот — это ещё один ub:
он подключается к control.sock аккаунтов, как ./ub, поэтому умеет всё то же самое — status, chats,
open (переписка вживую), tell, write, send, undo, set, approve, restart… — плюс accounts / use / all
для нескольких аккаунтов. Меню и карточки — кнопками; черновики (approve) — с кнопками; уведомления —
по CONTROL_BOT_NOTIFY. Язык интерфейса: английский по умолчанию (CONTROL_BOT_LANG), у каждого админа
свой — 🌐 в меню или /language.

Слушается только админов: CONTROL_BOT_ADMINS (id или @ник), по умолчанию — владельцы аккаунтов
userbot. Всем остальным бот молчит, а попытка пишется в лог и тебе в уведомления.

Несколько аккаунтов: бота держит один процесс userbot (файловая блокировка в корневом state/),
остальные ждут и подхватывают его, если тот процесс остановится.
"""
import asyncio
import fcntl
import hashlib
import html
import json
import re
import time

from telethon import Button, TelegramClient, events
from telethon.tl import functions, types

import accounts

CHUNK = 3900          # Telegram режет сообщения на 4096 символах
PAGE = 8              # чатов на страницу
LANGS = ("en", "ru")
_ALL_SUFFIX = {"restart", "pause", "resume", "status", "media"}
_DRAFT_OK = {"+", "ok", "ок", "да", "го", "отправь", "отправить", "👍", "yes", "y", "send"}
_DRAFT_FORCE = {"ok!", "ок!", "+!"}
_DRAFT_NO = {"-", "no", "нет", "не надо", "отмена", "не отправляй", "cancel", "👎", "n"}

# ── тексты интерфейса ────────────────────────────────────────────────────────
T = {
    "en": {
        "kb_status": "📊 Status", "kb_chats": "💬 Chats", "kb_drafts": "✋ Drafts", "kb_menu": "☰ Menu",
        "start": "👋 Userbot control bot. The buttons below are the main thing; any ub command can also be "
                 "typed as text (help lists them).",
        "help": (
            "Userbot control bot.\n\n"
            "Buttons below: 📊 Status · 💬 Chats (tap a person for a card with actions) · ✋ Drafts · ☰ Menu.\n"
            "Language: 🌐 in the menu or /language.\n\n"
            "Any ub command can be typed as text (without the dot and .ub), e.g.:\n"
            "  status · chats · open 3 · close · history @masha 30\n"
            "  tell @masha ask about the exam — an instruction the bot follows in its own words\n"
            "  write @masha hi, it's me — a message from you as is\n"
            "  note @masha her name is Anna — fix what the bot remembers about her\n"
            "  undo · drafts · ok 12 · edit 12 <text> · no 12 · redo 12\n"
            "  approve @masha on · set @masha delay 5-20 · allow @x · deny @x · mute @x\n"
            "  pause · resume · restart · reset · sync @x\n"
            "Bot's own commands:\n"
            "  accounts · use <name> · all <command> · language\n"
            "  logs — log screen (filters, ▶️ live) · logs live — straight to live · logs 100 — as text\n\n"
            "open <who> — that chat's conversation arrives here live; close — stop.\n"
            "Drafts come with buttons; reply to a draft card with your text to send it instead.\n"
            "Note: the output of typed commands comes from the userbot and is in Russian."),
        "running": "▶️ running", "paused": "⏸ <b>paused</b>", "asleep": "🌙 asleep until {t}",
        "thinking": "💭 thinking: {n}", "drafts_wait": "✋ waiting for approval: <b>{n}</b>",
        "approve_all": "✋ reply approval: on for everyone", "sleep": "🌙 sleep: {s}",
        "anon": "🎭 anonymous chat: @{a}",
        "b_status": "📊 Status", "b_chats": "💬 Chats", "b_drafts": "✋ Drafts", "b_drafts_n": "✋ Drafts ({n})",
        "b_pause": "⏸ Pause", "b_resume": "▶️ Resume", "b_log": "📜 Log", "b_help": "❓ Help",
        "b_accounts": "👥 Accounts", "b_refresh": "🔄 Refresh", "b_menu": "⬅️ Menu", "b_lang": "🌐 Language",
        "b_back_chats": "⬅️ Chats", "b_back_chat": "⬅️ To chat", "b_cancel": "Cancel",
        "s_account": "account", "s_persona": "persona", "s_model": "model", "s_free": "free",
        "s_queue": "queue: {n}", "s_noqueue": "no queue", "s_whitelist": "whitelist",
        "s_noncontacts": "non-contacts", "s_yes": "yes", "s_no": "no", "s_anon": "anonymous chat",
        "s_muted": "muted", "s_hints": "instructions", "s_sleep": "sleep", "s_off": "off",
        "s_asleep": "{span}, asleep until {t}", "s_approve": "approval", "s_all": "everyone",
        "s_chats": "chats: {c}", "s_chatcfg": "per-chat settings", "s_notify": "notifications",
        "s_media": "own media", "s_media_ask": "only when asked", "s_media_queue": "delayed: {n}",
        "s_calls": "calls", "s_thinking": "thinking now",
        "chats_title": "💬 <b>Chats</b>  ·  {p}/{n}",
        "chats_legend": "<i>✋ draft · 📝 instruction · 💭 thinking · 🔇 muted · (n) unread</i>",
        "c_anon": "🎭 anonymous chat",
        "c_not_allowed": "⛔ the bot doesn't reply to them (not whitelisted / deny / mute)",
        "c_muted": "🔇 muted", "c_thinking": "💭 the bot is thinking about a reply",
        "c_draft": "✋ draft #{n} is waiting", "c_hint": "📝 instruction: «{h}»",
        "c_approve": "✋ approval: {v}", "c_as_all": " (same as everyone)", "on": "on", "off": "off",
        "c_night": "🌙 at night: {v}", "c_night_reply": "replies", "c_night_sleep": "sleeps, like everyone",
        "c_settings": "⚙️ {s}", "c_watching": "👁 the conversation arrives here live",
        "c_undo_q": "🗑 <b>Delete the bot's last reply for both sides?</b>",
        "b_hist": "📜 History", "b_watch": "👁 Live", "b_unwatch": "🙈 Stop watching", "b_tell": "💡 Instruction",
        "b_write": "✍️ Write", "b_memory": "🧠 Memory", "b_undo": "🗑 Delete reply", "b_mute": "🔇 Mute",
        "b_unmute": "🔈 Unmute", "b_appr_on": "✋ Approval: on", "b_appr_off": "✋ Approval: off",
        "b_night_reply": "☀️ Reply at night", "b_night_sleep": "🌙 Sleep at night", "b_yes_delete": "🗑 Yes, delete",
        "b_send_n": "✅ Send #{n}", "b_dont_send": "❌ Don't send",
        "d_title": "✋ <b>Drafts</b>", "d_none": "✋ <b>No drafts</b>", "d_item": "<b>#{no}</b> → {who} · {age} min",
        "d_legend": "<i>✅ send · 🔁 rewrite · ❌ don't send. Your own text — reply to the draft card or "
                    "edit N text</i>",
        "card_head": "✋ draft #{no} → {who}", "card_hint": "(on your instruction: «{h}»)",
        "card_media": "+ media: {m}", "card_cap": ", text with it: «{c}»", "card_file": "+ file: {f}",
        "card_create": "+ create file: {f}",
        "card_help": "Reply to this message with your own text to send it instead. Also: + send · - drop · "
                     "redo [what to change]",
        "b_card_send": "✅ Send", "b_card_redo": "🔁 Rewrite", "b_card_no": "❌ Don't send",
        "done_sent": "✅ sent", "done_edited": "✏️ your text was sent instead",
        "done_replaced": "🔁 replaced by a newer draft", "done_redo": "🔁 rewriting — a new draft will come",
        "done_cancelled": "❌ not sent",
        "a_title": "👥 <b>Accounts</b>", "a_legend": "<i>● running · ○ not running · ✓ selected</i>",
        "p_tell": "💡 Write an instruction for <b>{name}</b> — the bot will follow it in its own words, as if it "
                  "decided itself (a topic, a question, «send a cat photo»).",
        "p_write": "✍️ Write a message for <b>{name}</b> — it goes <b>from you as is</b>, and the bot steps aside "
                   "in this chat for TAKEOVER_MINUTES.",
        "p_note": "🧠 What to remember or fix about <b>{name}</b>? E.g. «her name is Anna, not Masha» or «forget "
                  "about work». Nothing is sent to them.",
        "p_next": "<i>Your next message is the text. Changed your mind — «Cancel».</i>",
        "t_cancelled": "cancelled", "t_nothing": "nothing to cancel", "t_account": "account {a}",
        "t_account_down": "account {a} (not running now — will connect when it's up)",
        "t_watch": "👁 watching live", "t_unwatch": "🙈 stopped watching", "t_muted": "🔇 muted",
        "t_unmuted": "🔈 unmuted", "t_appr_on": "✋ approval on", "t_appr_off": "✋ approval off",
        "t_night_reply": "☀️ will reply at night", "t_night_sleep": "🌙 will sleep at night",
        "t_deleted": "🗑 deleted for both sides", "t_paused": "⏸ auto-replies paused",
        "t_resumed": "▶️ auto-replies on", "t_sending": "📤 sending", "t_dropped": "🗑 won't send",
        "t_redo": "🔁 rewriting — a new draft will come",
        "t_tell_ok": "📝 instruction for {name} saved — the bot will follow it",
        "t_write_ok": "✎ sent from you to {name}", "t_note_ok": "🧠 memory about {name} updated",
        "t_force": "they wrote more after this draft — the bot is preparing a new one. Send this anyway: ok! {n}",
        "use_usage": "use <name> — accounts shows the list", "no_account": "no account «{a}» — accounts",
        "all_usage": "all <command>, e.g. all pause", "none_running": "no account is running",
        "no_log": "no log ({f}) — the bot wasn't started with ./run.sh? (under systemd — journalctl)",
        "log_head": "── log {a}, last lines: {n} ──",
        "not_needed": "not needed in the bot: just close the chat. To stop auto-replies — pause",
        "not_running": "{a} is not running",
        "conn_lost": "{a}: connection dropped (restarting?) — try again in a couple of seconds",
        "no_answer": "{a} didn't answer in {t} s",
        "unavailable": "{a} is unavailable now (not running or restarting)", "conn_error": "{a}: connection error ({e})",
        "restarting": "restarting — reconnecting…", "back_online": "back online", "chat_open": ", chat {c} is open",
        "lang_set": "🌐 Language: English",
        "log_title": "📜 <b>Log {a}</b>", "log_empty": "(nothing here yet)",
        "f_all": "all", "f_chat": "chats", "f_err": "errors",
        "b_live": "▶️ Live", "b_stop": "⏸ Stop",
        "live_on": "🟢 live · updates every {s} s · auto-stop in {m} min",
        "live_off": "⏹ stopped", "live_timeout": "⏹ stopped after {m} min — ▶️ to continue",
        "t_live_on": "🟢 live log on", "t_live_off": "⏹ live log stopped",
    },
    "ru": {
        "kb_status": "📊 Статус", "kb_chats": "💬 Чаты", "kb_drafts": "✋ Черновики", "kb_menu": "☰ Меню",
        "start": "👋 Бот управления userbot. Кнопки внизу — главное; любые команды ub можно писать текстом "
                 "(help — все).",
        "help": (
            "Бот управления userbot.\n\n"
            "Кнопки внизу: 📊 Статус · 💬 Чаты (нажми человека — карточка с действиями) · ✋ Черновики · ☰ Меню.\n"
            "Язык: 🌐 в меню или /language.\n\n"
            "Любую команду ub можно написать текстом (без точки и .ub), например:\n"
            "  status · chats · open 3 · close · history @masha 30\n"
            "  tell @masha спроси про экзамен — указание, бот выполнит своими словами\n"
            "  write @masha привет, это я — сообщение от тебя как есть\n"
            "  note @masha её зовут Аня — поправить, что бот о ней помнит\n"
            "  undo · drafts · ok 12 · edit 12 <текст> · no 12 · redo 12\n"
            "  approve @masha on · set @masha delay 5-20 · allow @x · deny @x · mute @x\n"
            "  pause · resume · restart · reset · sync @x\n"
            "Команды самого бота:\n"
            "  accounts · use <имя> · all <команда> · language\n"
            "  logs — экран лога (фильтры, ▶️ вживую) · logs live — сразу вживую · logs 100 — текстом\n\n"
            "open <кто> — переписка этого чата будет приходить сюда вживую; close — перестать.\n"
            "Черновики приходят с кнопками; ответь на карточку своим текстом — он уйдёт вместо черновика."),
        "running": "▶️ работает", "paused": "⏸ <b>на паузе</b>", "asleep": "🌙 спит до {t}",
        "thinking": "💭 думает: {n}", "drafts_wait": "✋ ждут подтверждения: <b>{n}</b>",
        "approve_all": "✋ подтверждение ответов: вкл для всех", "sleep": "🌙 сон: {s}",
        "anon": "🎭 анонимный чат: @{a}",
        "b_status": "📊 Статус", "b_chats": "💬 Чаты", "b_drafts": "✋ Черновики", "b_drafts_n": "✋ Черновики ({n})",
        "b_pause": "⏸ Пауза", "b_resume": "▶️ Продолжить", "b_log": "📜 Лог", "b_help": "❓ Справка",
        "b_accounts": "👥 Аккаунты", "b_refresh": "🔄 Обновить", "b_menu": "⬅️ Меню", "b_lang": "🌐 Язык",
        "b_back_chats": "⬅️ Чаты", "b_back_chat": "⬅️ К чату", "b_cancel": "Отмена",
        "s_account": "аккаунт", "s_persona": "личность", "s_model": "модель", "s_free": "свободна",
        "s_queue": "очередь: {n}", "s_noqueue": "без очереди", "s_whitelist": "белый список",
        "s_noncontacts": "не-контакты", "s_yes": "да", "s_no": "нет", "s_anon": "анонимный чат",
        "s_muted": "заглушены", "s_hints": "указания", "s_sleep": "сон", "s_off": "выкл",
        "s_asleep": "{span}, сплю до {t}", "s_approve": "подтверждение", "s_all": "всё",
        "s_chats": "чаты: {c}", "s_chatcfg": "настройки чатов", "s_notify": "уведомления",
        "s_media": "свои медиа", "s_media_ask": "только по просьбе", "s_media_queue": "отложено: {n}",
        "s_calls": "звонки", "s_thinking": "думает сейчас",
        "chats_title": "💬 <b>Чаты</b>  ·  {p}/{n}",
        "chats_legend": "<i>✋ черновик · 📝 указание · 💭 думает · 🔇 заглушён · (n) непрочитанные</i>",
        "c_anon": "🎭 анонимный чат", "c_not_allowed": "⛔ бот ему не отвечает (нет в белом списке / deny / mute)",
        "c_muted": "🔇 заглушён", "c_thinking": "💭 бот сейчас думает над ответом",
        "c_draft": "✋ ждёт черновик #{n}", "c_hint": "📝 указание: «{h}»",
        "c_approve": "✋ подтверждение: {v}", "c_as_all": " (как у всех)", "on": "вкл", "off": "выкл",
        "c_night": "🌙 ночью: {v}", "c_night_reply": "отвечает", "c_night_sleep": "спит, как все",
        "c_settings": "⚙️ {s}", "c_watching": "👁 переписка приходит сюда вживую",
        "c_undo_q": "🗑 <b>Удалить у обоих последний ответ бота?</b>",
        "b_hist": "📜 История", "b_watch": "👁 Вживую", "b_unwatch": "🙈 Не смотреть", "b_tell": "💡 Указание",
        "b_write": "✍️ Написать", "b_memory": "🧠 Память", "b_undo": "🗑 Удалить ответ", "b_mute": "🔇 Заглушить",
        "b_unmute": "🔈 Включить", "b_appr_on": "✋ Подтв.: вкл", "b_appr_off": "✋ Подтв.: выкл",
        "b_night_reply": "☀️ Отвечать ночью", "b_night_sleep": "🌙 Спать ночью", "b_yes_delete": "🗑 Да, удалить",
        "b_send_n": "✅ Отправить #{n}", "b_dont_send": "❌ Не отправлять",
        "d_title": "✋ <b>Черновики</b>", "d_none": "✋ <b>Черновиков нет</b>", "d_item": "<b>#{no}</b> → {who} · {age} мин",
        "d_legend": "<i>✅ отправить · 🔁 переписать · ❌ не отправлять. Свой текст — ответь на карточку черновика "
                    "или edit N текст</i>",
        "card_head": "✋ черновик #{no} → {who}", "card_hint": "(по твоему указанию: «{h}»)",
        "card_media": "+ медиа: {m}", "card_cap": ", текст к нему: «{c}»", "card_file": "+ файл: {f}",
        "card_create": "+ создать файл: {f}",
        "card_help": "Ответь на это сообщение своим текстом — он уйдёт вместо черновика. Ещё: + отправить · "
                     "- не отправлять · redo [что иначе]",
        "b_card_send": "✅ Отправить", "b_card_redo": "🔁 Переписать", "b_card_no": "❌ Не отправлять",
        "done_sent": "✅ отправлен", "done_edited": "✏️ вместо него отправлен твой текст",
        "done_replaced": "🔁 заменён новым черновиком", "done_redo": "🔁 переписываю — придёт новый черновик",
        "done_cancelled": "❌ не отправлен",
        "a_title": "👥 <b>Аккаунты</b>", "a_legend": "<i>● запущен · ○ не запущен · ✓ выбран</i>",
        "p_tell": "💡 Напиши указание для <b>{name}</b> — бот выполнит его своими словами, как будто сам решил "
                  "(тема, вопрос, «скинь фото кота»).",
        "p_write": "✍️ Напиши сообщение для <b>{name}</b> — оно уйдёт <b>от тебя как есть</b>, а бот уступит тебе "
                   "чат на TAKEOVER_MINUTES.",
        "p_note": "🧠 Что запомнить или исправить о <b>{name}</b>? Например: «её зовут Аня, не Маша» или «забудь "
                  "про работу». Ему ничего не уходит.",
        "p_next": "<i>Следующее твоё сообщение — это он и есть. Передумал — «Отмена».</i>",
        "t_cancelled": "отменил", "t_nothing": "нечего отменять", "t_account": "аккаунт {a}",
        "t_account_down": "аккаунт {a} (сейчас не запущен — подключусь, когда поднимется)",
        "t_watch": "👁 смотрю вживую", "t_unwatch": "🙈 больше не смотрю", "t_muted": "🔇 заглушён",
        "t_unmuted": "🔈 снова отвечаю", "t_appr_on": "✋ подтверждение вкл", "t_appr_off": "✋ подтверждение выкл",
        "t_night_reply": "☀️ будет отвечать ночью", "t_night_sleep": "🌙 ночью будет спать",
        "t_deleted": "🗑 удалено у обоих", "t_paused": "⏸ автоответы на паузе", "t_resumed": "▶️ автоответы включены",
        "t_sending": "📤 отправляю", "t_dropped": "🗑 не отправляю", "t_redo": "🔁 переписываю — придёт новый черновик",
        "t_tell_ok": "📝 указание для {name} принято — бот выполнит", "t_write_ok": "✎ отправил от тебя: {name}",
        "t_note_ok": "🧠 память о {name} обновлена",
        "t_force": "после черновика он написал ещё — бот готовит новый. Отправить этот всё равно: ok! {n}",
        "use_usage": "use <имя> — accounts покажет список", "no_account": "нет аккаунта «{a}» — accounts",
        "all_usage": "all <команда>, например all pause", "none_running": "ни один аккаунт не запущен",
        "no_log": "лога нет ({f}) — бот запущен не через ./run.sh? (под systemd — journalctl)",
        "log_head": "── лог {a}, последние строки: {n} ──",
        "not_needed": "в боте это не нужно: просто закрой чат. Остановить автоответы — pause",
        "not_running": "{a} не запущен",
        "conn_lost": "{a}: соединение оборвалось (перезапускается?) — повтори через пару секунд",
        "no_answer": "{a} не ответил за {t} с",
        "unavailable": "{a} сейчас недоступен (не запущен или перезапускается)", "conn_error": "{a}: ошибка связи ({e})",
        "restarting": "перезапускается — переподключаюсь…", "back_online": "снова на связи", "chat_open": ", чат {c} открыт",
        "lang_set": "🌐 Язык: русский",
        "log_title": "📜 <b>Лог {a}</b>", "log_empty": "(пока пусто)",
        "f_all": "всё", "f_chat": "переписка", "f_err": "ошибки",
        "b_live": "▶️ Вживую", "b_stop": "⏸ Стоп",
        "live_on": "🟢 вживую · обновляется раз в {s} с · само остановится через {m} мин",
        "live_off": "⏹ остановлен", "live_timeout": "⏹ остановлен через {m} мин — ▶️, чтобы продолжить",
        "t_live_on": "🟢 живой лог включён", "t_live_off": "⏹ живой лог остановлен",
    },
}
MENU = {"en": [("menu", "main menu"), ("status", "bot status"), ("chats", "chats"), ("drafts", "drafts"),
               ("accounts", "accounts"), ("language", "language"), ("help", "help")],
        "ru": [("menu", "главное меню"), ("status", "состояние бота"), ("chats", "чаты"), ("drafts", "черновики"),
               ("accounts", "аккаунты"), ("language", "язык"), ("help", "справка")]}
LOG_LINES = 25        # строк в экране лога
LOG_EVERY = 3         # живой лог: раз в столько секунд (чаще Telegram не даёт править одно сообщение)
LOG_LIVE_MIN = 15     # живой лог сам останавливается через столько минут
_LOG_TIME = re.compile(r"^\d\d\.\d\d (\d\d:\d\d:\d\d) ")
_LOG_ERR = re.compile(r"error|ошибк|traceback|exception|не смог|не удалось|не вышло|упал|⚠️|внимание|"
                      r"warning|\[watchdog\]|не отвечает|timeout|таймаут", re.I)


def log_tail(path, filt: str, n: int = LOG_LINES, limit: int = 3300) -> str | None:
    """Последние строки лога для экрана: фильтр all / chat (← и →) / err; без даты, только время;
    не длиннее limit символов (сообщение Telegram — до 4096). None — файла нет."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 256 * 1024))   # хвоста в 256 КБ хватает и с фильтром
            lines = fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if size > 256 * 1024:
        lines = lines[1:]   # первая строка обрезана посередине
    if filt == "chat":
        lines = [x for x in lines if " ← " in x or "] → " in x]
    elif filt == "err":
        lines = [x for x in lines if _LOG_ERR.search(x)]
    out, total = [], 0
    for line in reversed(lines):
        line = _LOG_TIME.sub(r"\1 ", line.rstrip())
        if len(line) > 300:
            line = line[:299] + "…"
        if len(out) >= n or total + len(line) + 1 > limit:
            break
        out.append(line)
        total += len(line) + 1
    return "\n".join(reversed(out))


# надписи клавиатуры внизу — на обоих языках: старая клавиатура работает и после смены языка
KB_TEXT = {T[lg][k]: k[3:] for lg in LANGS for k in ("kb_status", "kb_chats", "kb_drafts", "kb_menu")}


def tr(lang: str, key: str, **kw) -> str:
    text = T.get(lang, T["en"]).get(key) or T["en"].get(key, key)
    return text.format(**kw) if kw else text


def log(*args) -> None:
    print("[бот управления]", *args, flush=True)


def H(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=False)


def short(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1] + "…"


def chunks(text: str) -> list[str]:
    """Длинный ответ (history, help) — на несколько сообщений, по границам строк."""
    out, cur = [], ""
    for line in (text or "—").split("\n"):
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
    return out or ["—"]


def cb(acc: str, act: str, arg="") -> bytes:
    """callback_data ≤ 64 байт: «u|аккаунт|действие|аргумент»."""
    return f"u|{acc}|{act}|{arg}".encode()[:64]


def btn(text: str, acc: str, act: str, arg="") -> Button:
    return Button.inline(text, cb(acc, act, arg))


async def oneshot(account: str, line: str, timeout: float = 180, lang: str = "en") -> str:
    """Одна команда аккаунту по отдельному соединению (как ./ub -a <имя> <команда>)."""
    try:
        reader, writer = await asyncio.open_unix_connection(str(accounts.control_sock(account)))
    except OSError:
        return tr(lang, "not_running", a=account)
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
        return tr(lang, "conn_lost", a=account)
    except TimeoutError:
        return tr(lang, "no_answer", a=account, t=int(timeout))
    except OSError as exc:
        return tr(lang, "conn_error", a=account, e=exc)
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
    и снова открывает чат, который был открыт. lang() — язык служебных фраз."""

    def __init__(self, account: str, on_msg, subscribe: bool = False, announce: bool = False, lang=lambda: "en"):
        self.account, self.on_msg, self.subscribe, self.announce, self.lang = account, on_msg, subscribe, announce, lang
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
                    lg = self.lang()
                    await self._say(tr(lg, "back_online") + (tr(lg, "chat_open", c=self.chat) if self.chat else ""))
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
                self.results.put_nowait(tr(self.lang(), "conn_lost", a=self.account))
            if self.announce and not lost_at:
                lost_at = time.time()
                await self._say(tr(self.lang(), "restarting"))

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
                return tr(self.lang(), "unavailable", a=self.account)
            while not self.results.empty():
                self.results.get_nowait()
            try:
                self._write({"line": line})
                await self.writer.drain()
            except (OSError, AttributeError):
                return tr(self.lang(), "unavailable", a=self.account)
            try:
                return await asyncio.wait_for(self.results.get(), timeout)
            except asyncio.TimeoutError:
                return tr(self.lang(), "no_answer", a=self.account, t=int(timeout))

    async def close(self) -> None:
        self.closed = True
        if self.task:
            self.task.cancel()
        if self.writer:
            self.writer.close()


class ControlBot:
    def __init__(self, token: str, api_id: int, api_hash: str, admins: list[str], notify_level: str,
                 own_account: str, owner_notify, default_lang: str = "en"):
        self.token, self.api_id, self.api_hash = token, api_id, api_hash
        self.admins_cfg = [a.strip() for a in admins if a.strip()]
        self.notify_level = notify_level
        self.own = own_account
        self.owner_notify = owner_notify          # уведомление в userbot (о чужих попытках)
        self.default_lang = default_lang if default_lang in LANGS else "en"
        self.tag = hashlib.sha1(token.encode()).hexdigest()[:10]
        self.bot: TelegramClient | None = None
        self.sessions: dict[int, dict] = {}       # admin id → {"account", "link"}
        self.pending: dict[int, dict] = {}        # admin id → ждём текст: {"act", "acc", "cid", "name"}
        self.monitor: dict[str, Link] = {}        # аккаунт → соединение для черновиков/уведомлений
        self.cards: dict[int, dict] = {}          # id карточки черновика → {"acc", "no", "uid", "draft"}
        self.strangers: set[int] = set()
        self.live: dict[int, dict] = {}           # admin id → живой лог: {"task", "msg", "acc", "filt"}
        self._admins_cache: tuple[float, set[int], set[str]] = (0.0, set(), set())
        self.lang_file = accounts.state_dir(accounts.MAIN) / f"control_bot_{self.tag}_lang.json"
        try:
            self.langs: dict[str, str] = json.loads(self.lang_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.langs = {}

    # ── язык ───────────────────────────────────────────────────────────────
    def lang(self, admin: int) -> str:
        return self.langs.get(str(admin), self.default_lang)

    def t(self, admin: int, key: str, **kw) -> str:
        return tr(self.lang(admin), key, **kw)

    def set_lang(self, admin: int, lang: str) -> None:
        """Выбор языка — у каждого админа свой, переживает перезапуск."""
        self.langs[str(admin)] = lang
        try:
            self.lang_file.write_text(json.dumps(self.langs), encoding="utf-8")
        except OSError as exc:
            log(f"язык не сохранил: {exc}")

    def keyboard(self, admin: int) -> list:
        k = [self.t(admin, x) for x in ("kb_status", "kb_chats", "kb_drafts", "kb_menu")]
        return [[Button.text(k[0], resize=True), Button.text(k[1], resize=True)],
                [Button.text(k[2], resize=True), Button.text(k[3], resize=True)]]

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

    # ── отправка ───────────────────────────────────────────────────────────
    async def send(self, chat_id: int, text: str, buttons=None, html_mode: bool = False) -> list:
        """Текст (длинный — несколькими сообщениями); кнопки — у последнего."""
        sent = []
        parts = [text] if html_mode else chunks(text)
        for i, part in enumerate(parts):
            try:
                sent.append(await self.bot.send_message(
                    chat_id, part, buttons=buttons if i == len(parts) - 1 else None,
                    parse_mode="html" if html_mode else None))
            except Exception as exc:  # noqa: BLE001 — админ ещё не нажал /start, заблокировал бота…
                log(f"не смог написать {chat_id}: {exc}")
                break
        return sent

    async def show(self, event, text: str, buttons, edit: bool) -> None:
        """Экран меню: по кнопке — на месте старого сообщения, по команде — новым."""
        if edit:
            try:
                await event.edit(text, buttons=buttons, parse_mode="html", link_preview=False)
                return
            except Exception as exc:  # noqa: BLE001
                if "not modified" in str(exc).lower():
                    return
        await self.send(event.sender_id, text, buttons, html_mode=True)

    def recipients(self) -> set[int]:
        ids, _ = self.admins()
        return ids | set(self.sessions)

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
        if s["account"] == account and s["link"]:
            return self.t(admin, "t_account", a=account)
        if s["link"]:
            await s["link"].close()

        async def live(acc: str, obj: dict, admin=admin) -> None:
            if obj.get("kind") in ("draft", "notify", "draft_done"):
                return   # это приходит через монитор, всем админам
            icon = "ℹ️ " if obj.get("kind") == "sys" else ""
            await self.send(admin, icon + self.tag_acc(acc) + obj.get("text", ""))

        link = Link(account, live, announce=True, lang=lambda: self.lang(admin))
        s["account"], s["link"] = account, link
        ok = await link.start()
        return self.t(admin, "t_account" if ok else "t_account_down", a=account)

    async def ask(self, admin: int, line: str) -> str:
        s = await self.session(admin)
        return await s["link"].request(line)

    async def acc_of(self, admin: int) -> str:
        return (await self.session(admin))["account"]

    async def run_on(self, admin: int, acc: str, line: str) -> str:
        return await oneshot(acc, line, lang=self.lang(admin))

    async def data(self, admin: int, acc: str, line: str):
        raw = await self.run_on(admin, acc, line)
        try:
            return json.loads(raw)
        except ValueError:
            return {"error": raw}

    # ── экраны ─────────────────────────────────────────────────────────────
    def state_line(self, admin: int, sm: dict) -> str:
        if sm["paused"]:
            return self.t(admin, "paused")
        return self.t(admin, "asleep", t=sm["sleep_until"]) if sm["asleep"] else self.t(admin, "running")

    async def menu_view(self, admin: int) -> tuple[str, list]:
        t = lambda k, **kw: self.t(admin, k, **kw)  # noqa: E731
        acc = await self.acc_of(admin)
        sm = await self.data(admin, acc, "__summary")
        if not isinstance(sm, dict) or "error" in sm:
            rows = [[btn(t("b_refresh"), acc, "menu"), btn(t("b_lang"), acc, "lang")]]
            if self.multi():
                rows.insert(0, [btn(t("b_accounts"), acc, "accs")])
            return f"⚠️ <b>{H(acc)}</b>: {H(sm.get('error') if isinstance(sm, dict) else sm)}", rows
        lines = [f"🤖 <b>{H(sm['me'])}</b>" + (f"  ·  <code>{H(acc)}</code>" if self.multi() else ""),
                 self.state_line(admin, sm) + (f"  ·  {t('thinking', n=sm['thinking'])}" if sm["thinking"] else "")]
        if sm["drafts"]:
            lines.append(t("drafts_wait", n=sm["drafts"]))
        if sm["approve"]:
            lines.append(t("approve_all"))
        if sm["sleep_on"]:
            lines.append(t("sleep", s=H(sm["sleep_span"])))
        if sm["anon"]:
            lines.append(t("anon", a=H(sm["anon"])))
        drafts = t("b_drafts_n", n=sm["drafts"]) if sm["drafts"] else t("b_drafts")
        pause = (t("b_resume"), "resume") if sm["paused"] else (t("b_pause"), "pause")
        rows = [[btn(t("b_status"), acc, "status"), btn(t("b_chats"), acc, "chats", 0)],
                [btn(drafts, acc, "drafts"), btn(pause[0], acc, pause[1])],
                [btn(t("b_log"), acc, "logs"), btn(t("b_help"), acc, "help")],
                [btn(t("b_lang"), acc, "lang"), btn(t("b_refresh"), acc, "menu")]]
        if self.multi():
            rows[-1].insert(0, btn(t("b_accounts"), acc, "accs"))
        return "\n".join(lines), rows

    async def status_view(self, admin: int, acc: str) -> tuple[str, list]:
        """Состояние — из данных (__summary), а не из готового текста userbot: так оно на языке админа."""
        t = lambda k, **kw: self.t(admin, k, **kw)  # noqa: E731
        sm = await self.data(admin, acc, "__summary")
        if "error" in sm:
            return f"⚠️ {H(sm['error'])}", [[btn(t("b_menu"), acc, "menu")]]

        def j(xs) -> str:
            return H(", ".join(xs)) if xs else "—"
        wl = j(sm["whitelist"]) + (f" + {j(sm['allow_add'])}" if sm["allow_add"] else "") \
            + (f" − {j(sm['allow_del'])}" if sm["allow_del"] else "")
        if sm["sleep_on"]:
            sleep = t("s_asleep", span=sm["sleep_span"], t=sm["sleep_until"]) if sm["asleep"] else sm["sleep_span"]
        else:
            sleep = t("s_off")
        approve = t("s_all") if sm["approve"] else t("s_off")
        if sm["approve_chats"] and not sm["approve"]:
            approve += "; " + t("s_chats", c=j(sm["approve_chats"]))
        model = t("s_queue", n=sm["queue"]) if sm["queue"] else (t("s_free") if sm["slots"] else t("s_noqueue"))
        media = j(sm["media"]) if sm["media"] else t("s_off")
        if sm["media"] and not sm["media_self"]:
            media += f" ({t('s_media_ask')})"
        if sm["media_queue"]:
            media += "; " + t("s_media_queue", n=sm["media_queue"])
        rows_txt = [
            (t("s_account"), H(f"{sm['account']} ({sm['me']})")), (t("s_persona"), H(sm["persona"])),
            (t("s_model"), model), (t("s_whitelist"), wl),
            (t("s_noncontacts"), t("s_yes") if sm["non_contacts"] else t("s_no")),
            (t("s_anon"), "@" + H(sm["anon"]) if sm["anon"] else "—"), (t("s_muted"), j(sm["muted"])),
            (t("s_hints"), j(sm["hints"])), (t("s_sleep"), H(sleep)), (t("s_approve"), approve),
            (t("s_chatcfg"), str(sm["chat_cfg"])), (t("s_notify"), H(sm["notify"])), (t("s_media"), media),
            (t("s_calls"), H(sm["calls"])), (t("s_thinking"), j(sm["thinking_names"]))]
        text = f"<b>{self.state_line(admin, sm)}</b>\n" + "\n".join(f"<b>{k}:</b> {v}" for k, v in rows_txt)
        pause = (t("b_resume"), "resume") if sm["paused"] else (t("b_pause"), "pause")
        return text, [[btn(pause[0], acc, pause[1]), btn(t("b_refresh"), acc, "status")],
                      [btn(t("b_menu"), acc, "menu")]]

    async def chats_view(self, admin: int, acc: str, page: int) -> tuple[str, list]:
        t = lambda k, **kw: self.t(admin, k, **kw)  # noqa: E731
        d = await self.data(admin, acc, f"__chats {page * PAGE} {PAGE}")
        if "error" in d:
            return f"⚠️ {H(d['error'])}", [[btn(t("b_menu"), acc, "menu")]]
        rows = []
        for c in d["items"]:
            flags = ("✋" if c["draft"] else "") + ("📝" if c["hint"] else "") + ("💭" if c["thinking"] else "") \
                + ("🔇" if c["muted"] else "")
            unread = f" ({c['unread']})" if c["unread"] else ""
            rows.append([btn(short(f"{flags}{c['name']}{unread} — {'→ ' if c['out'] else ''}{c['preview']}", 60),
                             acc, "chat", c["id"])])
        nav = []
        if page > 0:
            nav.append(btn("◀️", acc, "chats", page - 1))
        if d["more"]:
            nav.append(btn("▶️", acc, "chats", page + 1))
        if nav:
            rows.append(nav)
        rows.append([btn(t("b_menu"), acc, "menu"), btn("🔄", acc, "chats", page)])
        pages = max(1, (d["total"] + PAGE - 1) // PAGE)
        return t("chats_title", p=page + 1, n=pages) + "\n" + t("chats_legend"), rows

    async def chat_view(self, admin: int, acc: str, cid: int, ask_undo: bool = False) -> tuple[str, list]:
        t = lambda k, **kw: self.t(admin, k, **kw)  # noqa: E731
        c = await self.data(admin, acc, f"__chat {cid}")
        if "error" in c:
            return f"⚠️ {H(c['error'])}", [[btn(t("b_back_chats"), acc, "chats", 0)]]
        s = self.sessions.get(admin) or {}
        watching = s.get("account") == acc and s.get("link") and s["link"].chat_id == cid
        lines = [f"👤 <b>{H(c['name'])}</b>"]
        if c["anon"]:
            lines.append(t("c_anon"))
        elif not c["allowed"]:
            lines.append(t("c_not_allowed"))
        if c["muted"]:
            lines.append(t("c_muted"))
        if c["thinking"]:
            lines.append(t("c_thinking"))
        if c["draft_no"]:
            lines.append(t("c_draft", n=c["draft_no"]))
        if c["hint_text"]:
            lines.append(t("c_hint", h=H(short(c["hint_text"], 120))))
        lines.append(t("c_approve", v=t("on") if c["approve"] else t("off"))
                     + ("" if c["approve_own"] is not None else t("c_as_all")))
        if c["sleep_on"]:
            lines.append(t("c_night", v=t("c_night_reply") if c["sleep_off"] else t("c_night_sleep")))
        extra = {k: v for k, v in c["settings"].items() if k not in ("approve", "sleep")}
        if extra:
            lines.append(t("c_settings", s=", ".join(f"{k} {H(v)}" for k, v in extra.items())))
        if watching:
            lines.append(t("c_watching"))
        if c["preview"]:
            lines.append(f"\n<i>{'→ ' if c['out'] else '← '}{H(short(c['preview'], 120))}</i>")
        if ask_undo:
            lines.append("\n" + t("c_undo_q"))
            return "\n".join(lines), [[btn(t("b_yes_delete"), acc, "undo!", cid),
                                       btn(t("b_cancel"), acc, "chat", cid)]]
        rows = [[btn(t("b_hist"), acc, "hist", cid),
                 btn(t("b_unwatch") if watching else t("b_watch"), acc, "unwatch" if watching else "watch", cid)],
                [btn(t("b_tell"), acc, "ask_tell", cid), btn(t("b_write"), acc, "ask_write", cid)],
                [btn(t("b_memory"), acc, "info", cid), btn(t("b_undo"), acc, "undo", cid)],
                [btn(t("b_unmute") if c["muted"] else t("b_mute"), acc, "unmute" if c["muted"] else "mute", cid),
                 btn(t("b_appr_off") if c["approve"] else t("b_appr_on"), acc, "appr", cid)]]
        if c["sleep_on"]:
            rows.append([btn(t("b_night_sleep") if c["sleep_off"] else t("b_night_reply"), acc, "sleep", cid)])
        if c["draft_no"]:
            no = c["draft_no"]
            rows.insert(0, [Button.inline(t("b_send_n", n=no), f"d|{acc}|ok|{no}".encode()),
                            Button.inline(t("b_dont_send"), f"d|{acc}|no|{no}".encode())])
        rows.append([btn(t("b_back_chats"), acc, "chats", 0), btn("🔄", acc, "chat", cid)])
        return "\n".join(lines), rows

    async def drafts_view(self, admin: int, acc: str) -> tuple[str, list]:
        t = lambda k, **kw: self.t(admin, k, **kw)  # noqa: E731
        ds = await self.data(admin, acc, "__drafts")
        if isinstance(ds, dict):
            return f"⚠️ {H(ds.get('error'))}", [[btn(t("b_menu"), acc, "menu")]]
        if not ds:
            return t("d_none"), [[btn(t("b_menu"), acc, "menu"), btn("🔄", acc, "drafts")]]
        lines, rows = [t("d_title")], []
        for d in ds[:8]:
            media = f" + {', '.join(d['media'])}" if d["media"] else ""
            lines.append("\n" + t("d_item", no=d["no"], who=H(d["who"]), age=d["age_min"])
                         + f"\n{H(short(d['text'], 300))}{H(media)}")
            no = d["no"]
            rows.append([Button.inline(f"✅ #{no}", f"d|{acc}|ok|{no}".encode()),
                         Button.inline(f"🔁 #{no}", f"d|{acc}|redo|{no}".encode()),
                         Button.inline(f"❌ #{no}", f"d|{acc}|no|{no}".encode())])
        rows.append([btn(t("b_menu"), acc, "menu"), btn("🔄", acc, "drafts")])
        lines.append("\n" + t("d_legend"))
        return "\n".join(lines), rows

    async def accounts_view(self, admin: int) -> tuple[str, list]:
        on, cur = set(await running()), await self.acc_of(admin)
        rows = [[btn(f"{'●' if n in on else '○'} {n}{'  ✓' if n == cur else ''}", n, "use", n)]
                for n in accounts.list_accounts()]
        rows.append([btn(self.t(admin, "b_menu"), cur, "menu")])
        return self.t(admin, "a_title") + "\n" + self.t(admin, "a_legend"), rows

    def logs_view(self, admin: int, acc: str, filt: str = "all", live: str = "") -> tuple[str, list]:
        """Экран лога: хвост, фильтры, ▶️ Вживую / ⏸ Стоп. live — строка состояния живого режима."""
        t = lambda k, **kw: self.t(admin, k, **kw)  # noqa: E731
        path = accounts.state_dir(acc) / "userbot.log"
        tail = log_tail(path, filt)
        head = t("log_title", a=H(acc)) + f"  ·  {t('f_' + filt)}"
        if tail is None:
            body = H(t("no_log", f=path.name))
        else:
            body = f"<pre>{H(tail) if tail else H(t('log_empty'))}</pre>"
        text = head + ("\n" + live if live else "") + "\n" + body
        mark = lambda f: ("✓ " if f == filt else "") + t("f_" + f)  # noqa: E731
        on = admin in self.live and self.live[admin]["acc"] == acc
        rows = [[btn(mark(f), acc, "logs", f) for f in ("all", "chat", "err")],
                [btn(t("b_stop"), acc, "stop", filt) if on else btn(t("b_live"), acc, "live", filt),
                 btn("🔄", acc, "logs", filt), btn(t("b_menu"), acc, "menu")]]
        return text, rows

    async def live_loop(self, admin: int, acc: str, msg_id: int, filt: str) -> None:
        """Живой лог: то же сообщение правится раз в LOG_EVERY с, если в логе есть новое."""
        until = time.time() + LOG_LIVE_MIN * 60
        last = None
        try:
            while time.time() < until:
                text, rows = self.logs_view(admin, acc, filt, self.t(admin, "live_on", s=LOG_EVERY, m=LOG_LIVE_MIN))
                if text != last:
                    try:
                        await self.bot.edit_message(admin, msg_id, text, buttons=rows, parse_mode="html")
                    except Exception as exc:  # noqa: BLE001
                        if "not modified" not in str(exc).lower():
                            log(f"живой лог остановлен: {exc}")   # сообщение удалили и т.п.
                            return
                    last = text
                await asyncio.sleep(LOG_EVERY)
            self.live.pop(admin, None)
            text, rows = self.logs_view(admin, acc, filt, self.t(admin, "live_timeout", m=LOG_LIVE_MIN))
            try:
                await self.bot.edit_message(admin, msg_id, text, buttons=rows, parse_mode="html")
            except Exception:  # noqa: BLE001
                pass
        finally:
            if self.live.get(admin, {}).get("task") is asyncio.current_task():
                self.live.pop(admin, None)

    def stop_live(self, admin: int) -> dict | None:
        cur = self.live.pop(admin, None)
        if cur:
            cur["task"].cancel()
        return cur

    def lang_view(self, admin: int, acc: str) -> tuple[str, list]:
        cur = self.lang(admin)
        rows = [[btn(("✓ " if cur == "en" else "") + "🇬🇧 English", acc, "setlang", "en"),
                 btn(("✓ " if cur == "ru" else "") + "🇷🇺 Русский", acc, "setlang", "ru")],
                [btn(self.t(admin, "b_menu"), acc, "menu")]]
        return "🌐 <b>Language / Язык</b>", rows

    def card_text(self, admin: int, acc: str, no: int, d: dict, status: str = "") -> str:
        """Карточка черновика на языке админа (поля приходят из userbot)."""
        t = lambda k, **kw: self.t(admin, k, **kw)  # noqa: E731
        head = self.tag_acc(acc) + t("card_head", no=no, who=d.get("who", ""))
        if d.get("hint"):
            head += "\n" + t("card_hint", h=d["hint"])
        parts = [head]
        if d.get("reply"):
            parts.append(d["reply"])
        for a in d.get("acts") or []:
            if a[0] == "media":
                parts.append(t("card_media", m=a[1]) + (t("card_cap", c=d["caption"]) if d.get("caption") else ""))
            else:
                parts.append(t("card_file" if a[0] == "send" else "card_create", f=a[1]))
        parts.append(f"— {status}" if status else t("card_help"))
        return "\n\n".join(parts)

    def card_buttons(self, admin: int, acc: str, no: int) -> list:
        return [[Button.inline(self.t(admin, "b_card_send"), f"d|{acc}|ok|{no}".encode()),
                 Button.inline(self.t(admin, "b_card_redo"), f"d|{acc}|redo|{no}".encode())],
                [Button.inline(self.t(admin, "b_card_no"), f"d|{acc}|no|{no}".encode())]]

    async def screen(self, admin: int, name: str, event, edit: bool) -> None:
        acc = await self.acc_of(admin)
        if name == "language":
            text, rows = self.lang_view(admin, acc)
        else:
            view = {"menu": lambda: self.menu_view(admin), "status": lambda: self.status_view(admin, acc),
                    "chats": lambda: self.chats_view(admin, acc, 0), "drafts": lambda: self.drafts_view(admin, acc),
                    "accounts": lambda: self.accounts_view(admin)}
            text, rows = await view[name]()
        await self.show(event, text, rows, edit)

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
            d = obj.get("draft") or {"who": "?", "reply": obj.get("text", "")}
            for uid in self.recipients():
                for m in await self.send(uid, self.card_text(uid, acc, no, d), self.card_buttons(uid, acc, no)):
                    self.cards[m.id] = {"acc": acc, "no": no, "uid": uid, "draft": d}
            while len(self.cards) > 300:
                self.cards.pop(next(iter(self.cards)))
        elif kind == "draft_done":
            no, code = int(obj.get("no", 0)), obj.get("code") or "cancelled"
            for mid, c in list(self.cards.items()):
                if c["acc"] == acc and c["no"] == no:
                    status = self.t(c["uid"], f"done_{code}")
                    try:
                        await self.bot.edit_message(c["uid"], mid,
                                                    self.card_text(c["uid"], acc, no, c["draft"], status)[:4000],
                                                    buttons=None)
                    except Exception:  # noqa: BLE001 — сообщение могли удалить
                        pass
                    self.cards.pop(mid, None)
        elif kind == "notify":
            if self.notify_level == "off" or (self.notify_level == "important" and not obj.get("important")):
                return
            for uid in self.recipients():
                await self.send(uid, self.tag_acc(acc) + obj.get("text", ""))

    # ── текстовые команды ──────────────────────────────────────────────────
    async def handle_line(self, admin: int, line: str) -> str:
        parts = line.split()
        cmd = parts[0].lower()
        if cmd in _ALL_SUFFIX and any(x.lower() == "all" for x in parts[1:]):
            parts = ["all", cmd] + [x for x in parts[1:] if x.lower() != "all"]   # restart all = all restart
            cmd = "all"
        elif cmd == "all" and len(parts) > 1 and parts[1].lower() == "logs":
            parts, cmd = ["logs"] + parts[2:], "logs"   # all logs — в боте лог одного аккаунта
        if cmd in ("help", "h", "?") and len(parts) == 1:
            # по-русски — ещё и полный список команд userbot (он сам по-русски)
            return self.t(admin, "help") + ("\n\n" + await self.ask(admin, "help") if self.lang(admin) == "ru" else "")
        if cmd == "use":
            if len(parts) < 2:
                return self.t(admin, "use_usage")
            if parts[1] not in accounts.list_accounts():
                return self.t(admin, "no_account", a=parts[1])
            return await self.use(admin, parts[1])
        if cmd == "all":
            rest = " ".join(parts[1:])
            if not rest:
                return self.t(admin, "all_usage")
            on = await running()
            if not on:
                return self.t(admin, "none_running")
            res = await asyncio.gather(*(self.run_on(admin, n, rest) for n in on))
            return "\n\n".join(f"── {n} ──\n{r}" for n, r in zip(on, res))
        if cmd == "logs":
            return await self.logs_text(admin, next((int(x) for x in parts[1:] if x.isdigit()), 30))
        if cmd in ("exit", "quit", "q", "clear"):
            return self.t(admin, "not_needed")
        return self.tag_acc(await self.acc_of(admin)) + await self.ask(admin, line)

    async def logs_text(self, admin: int, n: int) -> str:
        acc = await self.acc_of(admin)
        path = accounts.state_dir(acc) / "userbot.log"
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                tail = fh.readlines()[-min(n, 300):]
        except OSError:
            return self.t(admin, "no_log", f=path.name)
        return self.t(admin, "log_head", a=acc, n=len(tail)) + "\n" + "".join(tail).rstrip()

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

    def toast(self, admin: int, act: str, res: str, ok_text: str | None = None, **kw) -> str:
        """Короткий ответ на кнопку на языке админа. Если команда ответила неожиданно (ошибка) — её текст как есть.
        Успех узнаём по значку, с которого начинается ответ userbot."""
        icon = {"ok": "📤", "edit": "📤", "no": "🗑", "redo": "🔁", "undo!": "🗑", "mute": "🔇", "unmute": "🔈",
                "tell": "📝", "write": "✎", "note": "🧠", "pause": "⏸", "resume": "▶️", "appr": "⚙️", "sleep": "⚙️"}
        key = {"ok": "t_sending", "edit": "t_sending", "no": "t_dropped", "redo": "t_redo", "undo!": "t_deleted",
               "mute": "t_muted", "unmute": "t_unmuted", "tell": "t_tell_ok", "write": "t_write_ok",
               "note": "t_note_ok", "pause": "t_paused", "resume": "t_resumed"}
        if act == "ok" and "ok!" in res:
            return self.t(admin, "t_force", n=kw.get("n", ""))
        if act in icon and res.startswith(icon[act]):
            return ok_text or (self.t(admin, key[act], **kw) if act in key else res)
        return res

    async def on_message(self, event) -> None:
        if not await self.check(event):
            return
        text = (event.raw_text or "").strip()
        if not text:
            return
        admin = event.sender_id
        card = self.cards.get(event.message.reply_to_msg_id or 0)
        if card:   # ответ на карточку черновика: «+», «-», «redo …» или свой текст
            line = self.draft_line(card["no"], text)
            res = await self.run_on(admin, card["acc"], line)
            await self.send(admin, self.tag_acc(card["acc"])
                            + self.toast(admin, line.split()[0].rstrip("!"), res, n=card["no"]))
            return
        if text in KB_TEXT:            # кнопки внизу экрана (на любом из языков)
            self.pending.pop(admin, None)
            await self.screen(admin, KB_TEXT[text], event, edit=False)
            return
        if text.startswith("/"):   # /status, /tell@имябота … → status, tell …
            first, _, rest = text[1:].partition(" ")
            text = (first.split("@", 1)[0] + (" " + rest if rest else "")).strip()
            if not text:
                return
        low = text.lower()
        if low in ("cancel", "отмена"):
            await self.send(admin, self.t(admin, "t_cancelled" if self.pending.pop(admin, None) else "t_nothing"))
            return
        wait = self.pending.pop(admin, None)
        if wait:                       # после «Указание» / «Написать» / «Память» — это и есть текст
            res = await self.run_on(admin, wait["acc"], f"{wait['act']} {wait['cid']} {text}")
            await self.send(admin, self.tag_acc(wait["acc"]) + self.toast(admin, wait["act"], res, name=wait["name"]),
                            [[btn(self.t(admin, "b_back_chat"), wait["acc"], "chat", wait["cid"])]])
            return
        if low == "start":
            await self.send(admin, self.t(admin, "start"), self.keyboard(admin))
            await self.screen(admin, "menu", event, edit=False)
            return
        if low in ("language", "lang", "язык"):
            await self.screen(admin, "language", event, edit=False)
            return
        if low.split()[0] in ("language", "lang", "язык") and low.split()[1:2] and low.split()[1] in LANGS:
            self.set_lang(admin, low.split()[1])
            await self.send(admin, self.t(admin, "lang_set"), self.keyboard(admin))
            return
        if low.split()[0] in ("logs", "log", "лог") and not any(x.isdigit() for x in low.split()[1:]):
            # logs — экран лога с фильтрами; logs live — сразу вживую; logs 100 — просто текстом (ниже)
            acc = await self.acc_of(admin)
            live = any(x in ("live", "вживую") for x in low.split()[1:])
            text, rows = self.logs_view(admin, acc, "all")
            sent = await self.send(admin, text, rows, html_mode=True)
            if live and sent:
                await self.start_live(admin, acc, "all", sent[0].id)
            return
        if low in ("menu", "меню", "status", "chats", "drafts", "accounts", "ls"):
            await self.screen(admin, {"меню": "menu", "ls": "chats"}.get(low, low), event, edit=False)
            return
        try:
            async with self.bot.action(admin, "typing"):
                res = await self.handle_line(admin, text)
        except Exception as exc:  # noqa: BLE001
            res = f"⚠️ {exc}"
        await self.send(admin, res)

    # ── кнопки ─────────────────────────────────────────────────────────────
    async def on_callback(self, event) -> None:
        if not await self.check(event):
            await event.answer("⛔")
            return
        admin = event.sender_id
        parts = event.data.decode(errors="replace").split("|")
        try:
            if parts[0] == "d" and len(parts) == 4:     # кнопки черновика
                _, acc, act, no = parts
                res = await self.run_on(admin, acc, f"{act} {no}")
                await event.answer(short(self.toast(admin, act, res, n=no), 190))
                if event.message_id not in self.cards:  # нажато в списке «Черновики» — обновим его
                    text, rows = await self.drafts_view(admin, acc)
                    await self.show(event, text, rows, edit=True)
                return   # карточку черновика обновит итог (draft_done)
            if parts[0] == "u" and len(parts) == 4:
                await self.on_ui(event, admin, parts[1], parts[2], parts[3])
                return
            await event.answer()
        except Exception as exc:  # noqa: BLE001
            log(f"кнопка {parts}: {exc}")
            try:
                await event.answer(f"⚠️ {exc}"[:190], alert=True)
            except Exception:  # noqa: BLE001
                pass

    async def start_live(self, admin: int, acc: str, filt: str, msg_id: int) -> None:
        self.stop_live(admin)   # у админа один живой лог: новый заменяет старый
        self.live[admin] = {"msg": msg_id, "acc": acc, "filt": filt, "task": None}
        self.live[admin]["task"] = asyncio.create_task(self.live_loop(admin, acc, msg_id, filt))

    async def on_ui(self, event, admin: int, acc: str, act: str, arg: str) -> None:
        s = await self.session(admin)
        if act == "setlang" and arg in LANGS:
            self.set_lang(admin, arg)
            await event.answer(self.t(admin, "lang_set"))
            await self.send(admin, self.t(admin, "lang_set"), self.keyboard(admin))   # клавиатура — на новом языке
            text, rows = await self.menu_view(admin)
            await self.show(event, text, rows, edit=True)
            return
        if act == "lang":
            await event.answer()
            text, rows = self.lang_view(admin, acc)
            await self.show(event, text, rows, edit=True)
            return
        if act == "use":
            await event.answer(await self.use(admin, arg))
            text, rows = await self.menu_view(admin)
            await self.show(event, text, rows, edit=True)
            return
        if acc != s["account"] and act not in ("chat", "chats"):
            await self.use(admin, acc)   # кнопка из экрана другого аккаунта — переходим в него
        views = {"menu": lambda: self.menu_view(admin), "status": lambda: self.status_view(admin, acc),
                 "drafts": lambda: self.drafts_view(admin, acc), "accs": lambda: self.accounts_view(admin)}
        if act in views:
            await event.answer()
            text, rows = await views[act]()
            await self.show(event, text, rows, edit=True)
            return
        if act == "chats":
            await event.answer()
            text, rows = await self.chats_view(admin, acc, int(arg or 0))
            await self.show(event, text, rows, edit=True)
            return
        cid = int(arg) if arg.lstrip("-").isdigit() else 0
        if act in ("pause", "resume"):
            await event.answer(short(self.toast(admin, act, await self.run_on(admin, acc, act)), 190))
            text, rows = await self.menu_view(admin)
            await self.show(event, text, rows, edit=True)
            return
        if act == "logs":   # из меню — новым сообщением (меню остаётся), из экрана лога — на месте
            await event.answer()
            in_log = arg in ("all", "chat", "err")
            filt = arg if in_log else "all"
            if in_log and admin in self.live and self.live[admin]["msg"] == event.message_id:
                await self.start_live(admin, acc, filt, event.message_id)
                return
            text, rows = self.logs_view(admin, acc, filt)
            if in_log:
                await self.show(event, text, rows, edit=True)
            else:
                await self.send(admin, text, rows, html_mode=True)
            return
        if act == "live":
            await event.answer(self.t(admin, "t_live_on"))
            await self.start_live(admin, acc, arg or "all", event.message_id)
            return
        if act == "stop":
            self.stop_live(admin)
            await event.answer(self.t(admin, "t_live_off"))
            text, rows = self.logs_view(admin, acc, arg or "all", self.t(admin, "live_off"))
            await self.show(event, text, rows, edit=True)
            return
        if act == "help":
            await event.answer()
            await self.send(admin, await self.handle_line(admin, "help"))
            return
        if act == "chat":
            await event.answer()
            text, rows = await self.chat_view(admin, acc, cid)
            await self.show(event, text, rows, edit=True)
            return
        if act in ("hist", "info"):
            await event.answer()
            await self.send(admin, await self.run_on(admin, acc, f"history {cid} 15" if act == "hist" else f"info {cid}"))
            return
        if act in ("watch", "unwatch"):
            if s["account"] != acc:
                await self.use(admin, acc)
            res = await self.sessions[admin]["link"].request(f"open {cid}" if act == "watch" else "close")
            await event.answer(self.t(admin, "t_watch" if act == "watch" else "t_unwatch"))
            if act == "watch":
                await self.send(admin, res)
            text, rows = await self.chat_view(admin, acc, cid)
            await self.show(event, text, rows, edit=True)
            return
        if act.startswith("ask_"):
            what = act[4:]
            c = await self.data(admin, acc, f"__chat {cid}")
            name = c.get("name", str(cid)) if isinstance(c, dict) else str(cid)
            self.pending[admin] = {"act": what, "acc": acc, "cid": cid, "name": name}
            await event.answer()
            await self.send(admin, self.t(admin, f"p_{what}", name=H(name)) + "\n\n" + self.t(admin, "p_next"),
                            [[btn(self.t(admin, "b_cancel"), acc, "cancel", cid)]], html_mode=True)
            return
        if act == "cancel":
            self.pending.pop(admin, None)
            await event.answer(self.t(admin, "t_cancelled"))
            try:
                await event.delete()
            except Exception:  # noqa: BLE001
                pass
            return
        if act == "undo":
            await event.answer()
            text, rows = await self.chat_view(admin, acc, cid, ask_undo=True)
            await self.show(event, text, rows, edit=True)
            return
        lines = {"undo!": f"undo {cid}", "mute": f"mute {cid}", "unmute": f"unmute {cid}"}
        ok_text = None
        if act in ("appr", "sleep"):
            c = await self.data(admin, acc, f"__chat {cid}")
            if act == "appr":
                lines[act] = f"approve {cid} {'off' if c.get('approve') else 'on'}"
                ok_text = self.t(admin, "t_appr_off" if c.get("approve") else "t_appr_on")
            else:
                lines[act] = f"set {cid} sleep {'-' if c.get('sleep_off') else 'off'}"
                ok_text = self.t(admin, "t_night_sleep" if c.get("sleep_off") else "t_night_reply")
        if act in lines:
            res = await self.run_on(admin, acc, lines[act])
            await event.answer(short(self.toast(admin, act, res, ok_text=ok_text), 190))
            text, rows = await self.chat_view(admin, acc, cid)
            await self.show(event, text, rows, edit=True)
            return
        await event.answer()

    # ── запуск ─────────────────────────────────────────────────────────────
    async def serve(self) -> None:
        session = accounts.state_dir(accounts.MAIN) / f"control_bot_{self.tag}"
        self.bot = TelegramClient(str(session), self.api_id, self.api_hash)
        self.bot.parse_mode = None   # текст как есть: в выводе команд бывают * _ ` [ ]
        await self.bot.start(bot_token=self.token)
        me = await self.bot.get_me()
        log(f"@{me.username} работает (аккаунт {self.own} держит бота)")
        # меню «/»: по умолчанию английское, у кого Telegram на русском — русское
        for code, lang in (("", "en"), ("ru", "ru")):
            try:
                await self.bot(functions.bots.SetBotCommandsRequest(
                    scope=types.BotCommandScopeDefault(), lang_code=code,
                    commands=[types.BotCommand(c, d) for c, d in MENU[lang]]))
            except Exception as exc:  # noqa: BLE001
                log(f"меню команд ({lang}) не задал: {exc}")
        self.bot.add_event_handler(self.on_message, events.NewMessage(incoming=True, func=lambda e: e.is_private))
        self.bot.add_event_handler(self.on_callback, events.CallbackQuery())
        mon = asyncio.create_task(self.monitor_loop())
        try:
            await self.bot.run_until_disconnected()
        finally:
            mon.cancel()
            for admin in list(self.live):
                self.stop_live(admin)
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
