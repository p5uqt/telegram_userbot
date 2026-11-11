# tg-llm-userbot

**English** | [Русский](README.ru.md)

A Telegram userbot that chats **on your behalf** using a language model — local (llama.cpp, Ollama, LM Studio) or cloud (OpenAI, DeepSeek, OpenRouter and any OpenAI-compatible API).

It writes like a real person: short messages, pauses and a "typing…" status, no emoji or corporate speak, and it keeps the conversation going on its own. It knows about you only what you write in `persona.md`.

> [!NOTE]
> The bot is Russian-first: its console messages, `ub` output and default phrases are in Russian. It answers in English when the other person writes in English, and you can add English phrases to `personality.toml` (`_en` keys).

---

## Features

- **Two modes**
  - **Private chats** — replies only to people on your whitelist (and optionally to everyone not in your contacts).
  - **Anonymous chat bot** (e.g. @AnonRuBot) — talks to random strangers and sends `/search` itself when a dialog ends.
- **Several accounts at once** — each with its own settings, and either a shared or its own personality (see [Multiple accounts](#multiple-accounts)).
- **Any model**: llama.cpp, Ollama, LM Studio, vLLM, OpenRouter, DeepSeek, OpenAI — anything that speaks the OpenAI API. Plus the native Ollama API and DeepSeek Harness.
- **Human-like behaviour**
  - pauses before reading and waits until the other person finishes a burst of messages;
  - "typing…" proportional to the reply length;
  - splits "statement + question" into two messages;
  - no trailing periods, no long dashes, no emoji and no robotic "I see, ...".
- **Never goes silent**: if the model returns nothing or a dry "ok", it asks the model again; as a last resort, a fallback phrase.
- **Understands anonymous-chat slang**: "м/д", "мд?", "м20", "го обмен".
- **Remembers what is already known** about the other person (gender, age) and doesn't ask again.
- **Sees photos, stickers, GIFs, videos and video messages** (optional, with a vision model), including view-once ones.
- **Listens to voice and video messages**: speech is recognised locally (faster-whisper), nothing goes to the cloud.
- **Reads files it receives** (text, code, .docx) and can send a file from its own folder.
- **Remembers people**: keeps a note about each person and uses it in later conversations.
- **Incoming calls**: can decline and write that you can't talk right now.
- **Sends your own photos, videos, voice and video messages** from the `media/` folder (optional): you decide what can go right away and what to stall on.
- **Steps aside for you**: if you write in a chat yourself, the bot stays quiet for a set time.
- **Control** from the terminal (`./ub`) and from Saved Messages: pause, status, live instructions to the bot, mute a person.

---

## Quick start

```bash
git clone https://github.com/<you>/tg-llm-userbot.git ~/tg-llm-userbot
cd ~/tg-llm-userbot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env              # fill in — see below
cp persona.example.md persona.md  # describe yourself

.venv/bin/python userbot.py --test-harness   # check that the model answers
.venv/bin/python userbot.py                  # first run: log in with your phone number
```

Requires **Python 3.11+** and `ffmpeg` (for voice messages, videos and sending your own media).

---

## Setting up `.env` step by step

All settings live in the `.env` file next to `userbot.py`. The full commented list is in [`.env.example`](.env.example).

### Step 1. Telegram API keys

1. Open https://my.telegram.org and log in with your phone number.
2. **API development tools** → create an application (any name and description).
3. Copy **App api_id** and **App api_hash**:

```ini
TG_API_ID=1234567
TG_API_HASH=0123456789abcdef0123456789abcdef
```

> These are *application* keys, not a password. Still, don't publish them.

### Step 2. Who to reply to

**Option A — private chats with a whitelist:**
```ini
ALLOW_USERS=@friend1, @friend2, 123456789, +380991234567
ALLOW_NON_CONTACTS=0    # 1 = also everyone who isn't in your contacts
ANON_BOT=
```
You can find someone's numeric id via bots like @userinfobot (forward them a message from that person).
A phone number (with `+`) works only if Telegram shows it to you: the person is in your contacts or has a public number.

**Option B — anonymous chat:**
```ini
ANON_BOT=AnonRuBot      # bot username, without @
AUTO_NEXT=1             # look for the next partner after a dialog ends
```
In this mode the bot replies **only** in that chat and ignores everyone else. Before the first run, open the bot manually once and complete its registration.

### Step 3. Model

Pick one option and put it in `.env`.

<details open>
<summary><b>llama.cpp (llama-server)</b> — local, maximum control</summary>

```ini
ENGINE=llamacpp
LLM_URL=http://127.0.0.1:8080/v1
LLM_MODEL=local          # = the server's --alias; barely matters with a single model
LLM_API_KEY=
LLM_THINK=0
LLM_VISION=0             # 1 if the server runs with --mmproj
```
Example server launch:
```bash
llama-server -hf unsloth/Qwen3.5-9B-GGUF:Q4_K_M -ngl 99 -c 16384 -fa on --jinja --alias local
```
`ENGINE=llamacpp` additionally sends parameters that only llama-server understands (`top_k`, `min_p`, toggling Qwen thinking). For other servers use `ENGINE=openai`.
</details>

<details>
<summary><b>Ollama</b></summary>

Via the OpenAI-compatible API (recommended, photos work too):
```ini
ENGINE=openai
LLM_URL=http://127.0.0.1:11434/v1
LLM_MODEL=qwen3:8b
```
Or the native Ollama API (lets you set the context size):
```ini
ENGINE=ollama
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:8b
OLLAMA_NUM_CTX=16384
OLLAMA_THINK=0
```
</details>

<details>
<summary><b>LM Studio / vLLM / another local server</b></summary>

```ini
ENGINE=openai
LLM_URL=http://127.0.0.1:1234/v1    # LM Studio; vLLM is usually :8000/v1
LLM_MODEL=model-name-from-the-server
```
</details>

<details>
<summary><b>OpenAI</b></summary>

```ini
ENGINE=openai
LLM_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...
```
</details>

<details>
<summary><b>DeepSeek API</b></summary>

```ini
ENGINE=openai
LLM_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_API_KEY=sk-...
```
</details>

<details>
<summary><b>OpenRouter</b> — hundreds of models with one key</summary>

```ini
ENGINE=openai
LLM_URL=https://openrouter.ai/api/v1
LLM_MODEL=qwen/qwen3-235b-a22b
LLM_API_KEY=sk-or-...
```
</details>

<details>
<summary><b>DeepSeek Harness (dsh)</b></summary>

```ini
ENGINE=dsh
DEEPSEEK_API_KEY=sk-...
BRIDGE_DSH_BIN=dsh       # or the full path to the binary
BRIDGE_PROFILE=headless
```
The agent runs `read-only` in the `sandbox/` folder: text from strangers ends up in the prompt, so it must not touch the machine.
</details>

Check — the bot answers "привет, как дела?" ("hi, how are you?") and exits:
```bash
.venv/bin/python userbot.py --test-harness
```

> [!TIP]
> **Which model to use.** Bigger is livelier and more obedient. 7–9B models often mix up roles and ignore rules. A good choice for 8 GB of VRAM is an MoE model like `Qwen3.x-30B/35B-A3B` in llama.cpp with `--n-cpu-moe`: almost as fast as an 8B, but much smarter. Cloud models work well, but your conversations go to the provider.

### Step 4. About you

```ini
OWNER_GENDER=m     # m | f — how to answer "м/д" (male/female?)
```
Everything else goes into `persona.md` (see below).

### Step 5. Behaviour (optional)

| Variable | Default | What it does |
|---|---|---|
| `READ_DELAY_MIN` / `READ_DELAY_MAX` | `15` / `90` | pause before reading, seconds (private chats) |
| `TYPING_CHARS_PER_SECOND` | `5` | "typing" speed: the longer the message, the longer "typing…" shows before sending |
| `TYPING_MAX_SECONDS` | `30` | cap on "typing…" per message, seconds |
| `TYPING_FIRST_SECONDS` / `TYPING_NEXT_SECONDS` | `-1` / `-1` | minimum "typing…" before the first / each next message of a reply, seconds; `-1` — automatic by length |
| `MAX_REPLY_CHARS` | `230` | longer replies are cut to the first sentences |
| `QUIET_SECONDS` | `12` | wait until the other person finishes a burst of messages |
| `TAKEOVER_MINUTES` | `30` | you wrote yourself in the last N minutes — the bot stays quiet |
| `MAX_REPLIES_PER_HOUR` | `20` | reply limit per hour per chat |
| `HISTORY_MESSAGES` | `40` | how many history messages the model sees |
| `DISCLOSURE_TEXT` | empty | first message in every new private chat (a notice that an AI is replying); empty — no notice, but a direct "are you a bot?" gets an honest answer |
| `NOTIFY` | `1` | copy replies and errors to Saved Messages |
| `ANON_MAX_REPLIES_PER_HOUR` | `60` | limit in the anonymous chat |
| `ANON_HISTORY_MESSAGES` | `24` | history in the anonymous chat |
| `ANON_TAKEOVER_MINUTES` | `2` | pause if you wrote in the anonymous chat yourself |
| `ANON_IDLE_MINUTES` | `6` | the anonymous partner is silent for N minutes after our message — `/next` (`0` — off; private chats are not affected) |
| `ANON_DISCLOSURE_TEXT` | empty | if set — sent to every new anonymous partner |
| `CALLS` | `ignore` | incoming calls: `ignore` — leave alone, `decline` — decline, `decline_text` — decline and write that you can't talk |
| `CALL_DECLINE_MIN` / `CALL_DECLINE_MAX` | `4` / `12` | after how many seconds to decline a call |
| `TYPO_CHANCE` | `0.06` | share of replies with a "phone-style" typo (`0` — no typos) |
| `TYPO_FIX_CHANCE` | `0.35` | share of typos the bot corrects right away with a `*word` message (`1` — always) |
| `LLM_TEMP` | `0.7` | model "creativity" |
| `LLM_MAX_TOKENS` | `300` | max tokens per reply |
| `LLM_TIMEOUT_SECONDS` | `240` | how long to wait for the model |
| `LLM_PARALLEL` | `1` | how many replies the model computes at once across all accounts; the rest wait in a queue. `0` — no queue (cloud API) |
| `PERSONA` | empty | personality from `personas/<name>/` (usually set in `accounts/<account>/.env`, see [Multiple accounts](#multiple-accounts)) |
| `TG_TIMEOUT_SECONDS` | `60` | timeout for Telegram requests |
| `WORKER_MAX_SECONDS` | `900` | a reply "hanging" longer than this is dropped and regenerated once |
| `MEMORY_SUMMARY_EVERY` | `10` | after how many new messages to update the note about a person |
| `MEMORY_BOOTSTRAP_MESSAGES` | `400` | how many latest messages to read when a chat is first seen; `0` — the whole conversation |
| `MEMORY_LOG_LINES` | `300` | how many latest lines of the conversation to keep in `state/contacts/<id>.md`; older ones go to the archive. `0` — never archive |
| `SYNC_ALL_CONTACTS` | `1` | after start, go through all recent chats (up to 200) and add what happened while the bot was off to memory; `0` — don't scan, a chat's memory updates when a new message arrives in it |
| `SYNC_CONTACTS` | empty | who to scan on start anyway, even with `SYNC_ALL_CONTACTS=0`: `@nick`, id, `+phone`, comma-separated. Manually — the `sync <who>` command |

For testing, it's handy to set `READ_DELAY_MIN=0`, `READ_DELAY_MAX=0`, `QUIET_SECONDS=0`.

---

## `persona.md` — who you are

The model knows about you **only** what is written in this file. Start from the template:
```bash
cp persona.example.md persona.md
```

What to write so the bot sounds alive:
- **Facts**: name, age, city, work/study, hobbies.
- **Concrete details and stories** — the most important part. Not "I like TV shows" but "I've rewatched Breaking Bad twice". The model will share them in conversation.
- **How you write** + 4–6 examples of your real messages.
- **What not to say.**

`persona.md` is in `.gitignore` — your data won't end up in the repository.

---

## `personality.toml` — how the bot behaves

`persona.md` is **who you are** (facts about you). `personality.toml` is **how the bot talks**:
rules, manner, ready-made phrases. Start from the template:
```bash
cp personality.example.toml personality.toml
```
If there is no `personality.toml`, `personality.example.toml` is used.

| Key | What it is |
|---|---|
| `name` | the name the bot introduces itself with |
| `gender` | `m` / `f` — grammatical gender of its messages and the answer to "мд?" (otherwise `OWNER_GENDER` from `.env`) |
| `rules` | the main prompt: conversation rules. Placeholders `{disclosure_note}` `{my_g}` `{my_g_note}` `{examples}` |
| `style_examples` | manner examples "their line \n my reply"; 3 random ones go into each chat |
| `hook_ideas` | how to revive a fading conversation |
| `meet_deflect` | excuses when asked to meet / call |
| `laughs` | reaction to a funny sticker |
| `howru_short` / `howru_followup` | short answer to "and how are you?" and the question after it |
| `fallback_replies` | if the model stayed silent twice |
| `already_answered` | the other person repeats a question that was already answered |
| `said_already` | the model keeps repeating its previous reply |
| `shady_refusals` | refusal when invited into something shady and the model agreed |
| `snap_backs` | snap back when insulted and the model keeps agreeing ("yes, I'm stupid") |
| `[now_activities]` | what you're "doing now" by time of day — the answer to "what are you up to?" (optional) |

Phrase keys can have an English variant with the `_en` suffix (`laughs_en`,
`fallback_replies_en`, etc.) — used when the other person writes in English.
All keys from `name` to `howru_followup` are required, except `gender`. The phrases
`fallback_replies` … `snap_backs` are optional — defaults from the code are used otherwise.

The bot sends phrases from this file as is, without the model — write them in your own grammatical gender.

`personality.toml` is in `.gitignore`.

---

## Logging in

**The usual way** — on the first run `userbot.py` asks for your number, the code from Telegram and the cloud password (if enabled).

**Non-interactive** (e.g. on a server):
```bash
.venv/bin/python login.py +79991234567     # a code arrives in Telegram
.venv/bin/python login.py code 12345
.venv/bin/python login.py password 'cloud password'   # only if 2FA is on
```

**With a QR code**: `.venv/bin/python qr_login.py` → in Telegram on your phone: Settings → Devices → Link Desktop Device.

The session is stored in `state/account.session`.

> [!CAUTION]
> `state/account.session` is **full access to your account**, with no password or 2FA. Never send it to anyone or commit it (it's in `.gitignore`). If it leaks — Settings → Devices → terminate the session.

### Multiple accounts

You can connect as many accounts as you like — they all reply at the same time, each in its own process.

- **`main`** — the main account: no flag, files in the root (`.env`, `state/`). Optional.
- **Others** — with the `-a <name>` flag, files in `accounts/<name>/`.

```bash
.venv/bin/python login.py -a work +79991234567   # -a <name> on every login step
.venv/bin/python login.py -a work code 12345
.venv/bin/python login.py -a work password '...' # only if 2FA is on
.venv/bin/python qr_login.py -a work             # or via QR
```

Logging in creates the account folder:
```
userbot/
├── .env                  ← shared settings (and main's settings)
├── persona.md            ← shared personality
├── personality.toml
├── media/
├── state/                ← main: login, memory, log
├── accounts/
│   └── work/
│       ├── .env          ← (optional) only the differences from the shared .env
│       ├── personality.toml, persona.md, media/   ← (optional) own personality
│       └── state/        ← work: login, memory, log
└── personas/
    └── katya/            ← (optional) a personality for several accounts
```

**Settings.** Without its own `.env`, an account takes everything from the root `.env` and behaves like `main`.
You create `accounts/<name>/.env` by hand and put **only the differences** in it — for example,
one account replies to strangers and another doesn't:
```ini
# accounts/work/.env
ALLOW_NON_CONTACTS=1
ALLOW_USERS=@friend1,@friend2
```
An empty value counts too: `ALLOW_USERS=` means an empty whitelist even if the root one is filled in.
Set the Telegram keys, the model and `LLM_PARALLEL` only in the root `.env`.

**Personality.** Shared by default. `persona.md`, `personality.toml` and `media/` are looked up in order —
each one separately, the first found wins:

1. `personas/<name>/` — if the account's `.env` has `PERSONA=<name>`. Several accounts can share such a personality.
2. `accounts/<account>/` — a personality for this account only.
3. the root — the shared personality.

You can override just part of it: e.g. put only `personality.toml` into `accounts/work/`
(own name and manner) while the `persona.md` biography stays shared. `status` shows where each part comes from.

> [!WARNING]
> If an account has its own personality but no `media/` of its own, it will send photos and voice messages from the shared one.
> Give it its own `media/` or turn media off: `MEDIA_SEND=` in its `.env`.

Each account always has its own login and memory about people. The `files/` folder is shared
(set a separate one with `FILES_DIR=` in the account's `.env`).

**Running.** `./run.sh` finds and starts every account you've logged into (or only the listed ones:
`./run.sh main work`); if one crashes, the others keep working. The `-a` flag is only needed
for logging in and for manual commands (`userbot.py -a work`, `./ub -a work status`).

**Model queue.** There is one model for everyone, so it computes at most `LLM_PARALLEL` replies
at once (1 by default); other accounts wait in a queue (the log says
`[llm] модель занята… жду в очереди` — "model busy, waiting in queue"). For a cloud API use `LLM_PARALLEL=0` — no queue.

**Without a main account.** If the root has no login, `run.sh` and `ub` work only with `accounts/`.
The root `.env` is still needed (shared settings). Don't run `login.py` without `-a` — it would log
into `main`. To turn the current `main` into a named account (with the bot stopped):
`mkdir -p accounts/<name> && mv state accounts/<name>/state && mkdir state`.

---

## Running

```bash
./run.sh                       # bot in the background with auto-restart + the ub console (see "Control")
.venv/bin/python userbot.py    # or just like this: log to the terminal, no auto-restart
```

Autostart with systemd (user service):
```bash
# fix the path in userbot.service if you didn't clone into ~/tg-llm-userbot
cp userbot.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now userbot
journalctl --user -u userbot -f      # logs
```

Several accounts under systemd — the `userbot@.service` template (instead of `userbot.service`):
```bash
cp userbot@.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now userbot@main userbot@work
```

Only one instance per account can run (`state/userbot.lock`). Don't run `send.py` or `login.py` while the bot is running: they share the session file.

---

## Control

### The `ub` program

`./run.sh` starts the bot in the background and immediately opens `ub` — a command line. The bot's log
doesn't clutter the screen: it goes to `state/userbot.log` (for other accounts — `accounts/<name>/state/userbot.log`;
every start gets a new log, the previous one moves to `userbot.log.1`), and you can view it with `logs`
(Ctrl+C — back to `ub`). If the bot restarts (watchdog), `ub` reconnects by itself.

```
$ ./run.sh
бот работает. help — команды, logs — лог бота, exit — остановить бота
ub> chats                     # recent chats with numbers
 1. Masha (@masha) 📝 (2) — а ты чем занята?
ub> open 1                    # open a chat: history + new messages live
[09.11 23:41] ← Masha: привет
[09.11 23:41] → бот: привет) как дела?
[09.11 23:42] ✎ ты: это я сам
ub[Masha (@masha)]> tell steer the conversation to the concert on Saturday
ub[Masha (@masha)]> logs      # bot log; Ctrl+C — back
ub[Masha (@masha)]> exit      # stop the bot
```
(`←` the other person, `→ бот` the bot, `✎ ты` you.)

- `./ub` — connect to an already running bot from **another** terminal (there `exit` closes
  only `ub`, the bot keeps running). `./ub status` — one command and exit.
- **Several accounts**: `ub` starts in **general mode** (`ub>`): there `logs` is the combined log of all
  accounts (lines tagged `[name]`), `accounts` — list and which are running, `all <command>` — run on all
  at once (`all pause`, `all restart`). `use work` — enter an account (`ub[work]>`): now `logs` shows only its
  log, and `chats`, `open`, `tell` and the other bot commands apply to it; `logs all` — still all of them.
  `use` without a name — back to general mode. `./ub -a work` — straight into an account, `./ub -a work status` —
  one command for a specific account. `restart` restarts only the current account: after changing
  code, the shared `.env` or the shared personality use `all restart` (each one waits for its own replies).
- `./run.sh --log` — the old mode: no `ub`, the whole log straight to the terminal. `run.sh` also
  behaves like this without a terminal (nohup, `> file`). Under systemd `./ub` works too, but the log is
  `journalctl --user -u userbot -f`, not `logs`.

| Command | Action |
|---|---|
| `help [command]` | list of commands / details about one |
| `status` | pause, account and personality, whitelist, muted, instructions, who is "thinking" now |
| `chats [n]` | recent private chats with numbers (📝 — has an instruction, 💭 — bot is thinking, 🔇 — muted) |
| `open <who>` / `close` | open a chat: history + new messages live (← them, → bot, ✎ you). `<who>` — `@nick`, nick or name without @ (as in `ls`, a prefix works: `open alex`), number from `ls`, id. Same as `cd <who>`; `cd` / `cd ..` — close |
| `history [who] [n]` | last n messages (20 by default) |
| `tell [who] <text>` | instruction for the bot: a topic, a question, "send a photo of the cat" |
| `forget [who]` | cancel the instruction |
| `note [who] [text]` | memory about a person: remember / correct / forget a fact or a standing directive; nothing is sent to them. Without text — show the memory |
| `sync [who\|all] [full]` | add the conversation with a person to memory right now (what happened without the bot); `all` — with everyone the bot has memory about plus whitelisted people; `full` — re-read the whole conversation from the start and rebuild the note; nothing is sent to anyone |
| `write [who] <text>` | send a message yourself (the bot yields the chat for `TAKEOVER_MINUTES`) |
| `send [who] <file>` | send media from `media/` right away, without the model |
| `media` | list of media with descriptions |
| `restart [cancel]` | restart the bot (current account) once it finishes the current replies (after changing `.env`, `personality.toml`, code); all accounts — `all restart` |
| `pause` / `resume` | stop / resume auto-replies; after `resume` the bot answers what came in during the pause (no older than a day) |
| `mute [who]` / `unmute [who]` | don't reply to a specific person |
| `accounts` | list of accounts: which are running, which is current |
| `use [name]` | enter an account; without a name — back to general mode `ub>` |
| `all <command>` | run a command on all running accounts (`all pause`, `all status`) |
| `logs [n]` | live log: last n lines (40 by default) and new ones; in general mode — all accounts, inside an account — only its own; Ctrl+C — back |
| `logs all [n]` | logs of all accounts, even from inside an account |
| `clear` | clear the screen |
| `exit` | from `./run.sh` — stop the bots of all accounts; from `./ub` — just leave (Ctrl+D — same) |

`<who>` — `@username`, numeric id, a number from `chats` or `anon` (the anonymous chat). If a chat
is opened with `open`, you can omit `<who>`. Tab completion and command history (↑/↓) work;
Ctrl+C clears the line, and in an open chat with an empty line it closes the chat (like `close`). You can open several `ub` at once — e.g. a different chat in each.

### From Telegram: Saved Messages

The same commands can be written in **Saved Messages** with the `.ub` prefix:
`.ub help`, `.ub status`, `.ub tell @masha …`, `.ub send @masha cat.jpg` etc.
Only the `ub`-specific commands (`open`, `close`, `logs`, `clear`, `exit`) don't work there.

If you write in a chat yourself, the bot notices and yields to you for `TAKEOVER_MINUTES`.

### Memory about a person: `note`

`tell` is a one-off instruction after which the bot writes. `note` edits what the bot **remembers** about
a person (`state/contacts/<id>.md`): it sends nothing and takes it into account in later replies.

```
ub> open @masha
ub[Masha (@masha)]> note she's not Anya, he's Andrey
ub[Masha (@masha)]> note forget that he likes anime
ub[Masha (@masha)]> note try harder to find out his surname
ub[Masha (@masha)]> note          # show what the bot remembers about them
```

- Write in your own words — the model corrects the note from the conversation itself and records what you said in a
  separate "From the owner" section. It takes priority over the note and the Telegram name, and auto-summaries don't overwrite it.
- It's permanent and survives restarts. To undo, also use words: `note forget about the surname`.
- Without an open chat: `note @masha …`; from Saved Messages: `.ub note @masha …`. There's no memory in the anonymous chat.
- You can edit the file by hand too — it's re-read on every reply.

### Live instructions: `.ub tell`

While the bot is chatting, you can nudge it from Saved Messages without stepping into the chat:

```
.ub tell @masha steer the conversation to the concert on Saturday
.ub tell @masha ask how her exam went
.ub tell @masha send her a photo of the cat
.ub tell anon say you have to go
```

- The other person doesn't see the instruction: the bot carries it out in its own words, as if it decided to.
- If the other person is silent, the bot writes to them itself, right away (no "reading" pause).
- If the bot is in the middle of a reply, the unfinished reply is thrown away and regenerated
  with the instruction (as if you added a message while it was thinking).
- A new instruction replaces the old one. A fulfilled one is removed automatically (you get ✅ in Saved Messages),
  an unfulfilled one is forgotten after 30 minutes.
- On instruction, media is sent even with `MEDIA_SELF=0` and `MEDIA_SEND` off,
  and right away — no stalling. To send a specific file exactly, without the model — `.ub send`.

---

## Photos (vision)

If the model can see images, the bot passes it the other person's last 2 photos (downscaled to 768 px):
```ini
LLM_VISION=1
```
- **llama.cpp**: the server must run with `--mmproj mmproj-file.gguf` (downloaded automatically with `-hf`).
- **Cloud / Ollama /v1**: choose a model with image support.

Without `LLM_VISION=1` the model only sees a "[photo]" marker and knows it can't see the content.

The model also sees stickers and GIFs (one frame), videos and video messages (`VIDEO_FRAMES` frames as one
grid image; videos heavier than `VIDEO_MAX_MB` — preview only). The bot views view-once photos/videos
and "opens" them after replying — they burn, as if you opened them yourself.

---

## The other person's voice and video messages

Speech is recognised locally with `faster-whisper` (CPU, needs `ffmpeg`); the model gets the text and
replies as if it listened. Transcripts are cached in `state/voice_cache.json`.

| Variable | Default | What it does |
|---|---|---|
| `WHISPER_MODEL` | `small` | `tiny` / `base` / `small` / `medium` / `large-v3`; empty or `0` — off |
| `WHISPER_THREADS` | `4` | CPU threads |
| `WHISPER_LANGUAGE` | empty | `ru` / `uk` / `en`; empty — auto-detect |
| `VOICE_MAX_SECONDS` | `300` | the bot "doesn't listen" to longer voice messages |

The whisper model downloads itself on the first run. If recognition is off, the bot asks to write in text.

---

## Files

Received text files (`.txt`, `.md`, code, `.csv`, `.docx` etc., up to 300 KB) are read by the model and
it replies based on their content. From the `FILES_DIR` folder (`files/` next to the bot by default) the bot can
send a file if asked, and it saves text files it creates there.
Put only what you don't mind giving to anyone the bot replies to into this folder. `FILES_SEND=0` turns off
sending and creating files entirely (received files are still read).

---

## Memory about people

For every private chat the bot keeps a file `state/contacts/<id>.md`: a short "what I know about them" note
(written by the model every `MEMORY_SUMMARY_EVERY` new messages) and the conversation log. The note goes into
the prompt, so the bot doesn't ask about what it already knows. You can edit or delete the file by hand — then
the memory about that person starts over. No memory is kept in the anonymous chat.

The model writes the note in order: everything not yet summarised is processed in batches of 200 messages,
oldest first, and the note is saved after each batch. So a long conversation is read in full, not just its tail.
When a chat is first seen, the latest `MEMORY_BOOTSTRAP_MESSAGES` messages are read (`0` — the whole conversation).
To re-read an already known chat from the very beginning and rebuild the note — `sync <who> full` (runs in the
background; what you said about the person yourself via `note` is kept). For everyone at once —
`sync all` (append what is new) or `sync all full` (re-read everything): that is everyone the bot already has memory
about plus whitelisted people among the latest 200 chats; in the general `ub>` mode the command goes to all accounts.

So the file doesn't grow forever (it is read and rewritten on every reply), it keeps the latest
`MEMORY_LOG_LINES` lines of the conversation, and older ones are moved to `state/contacts/archive/<id>.md`.
Only messages already covered by the note are archived — anything the model hasn't summarised yet stays in the file,
so nothing is lost from the memory about the person. Lines move in batches (once the log is ~20% over the limit);
the bot never reads the archive itself — it is for you; `info` shows how many messages are archived.

---

## Your own photos, videos, voice and video messages

The bot can send the other person your ready-made photos, videos, voice and video messages.
Off by default.

### Settings in `.env`

| Variable | Default | What it does |
|---|---|---|
| `MEDIA_SEND` | empty (off) | what may be sent, comma-separated: `photo`, `video`, `voice`, `round` or `all` |
| `MEDIA_SELF` | `0` | `0` — only when the other person asks; `1` — may also send on its own when it fits |
| `MEDIA_DIR` | `media/` next to the bot | media folder |
| `MEDIA_LATER_MIN` / `MEDIA_LATER_MAX` | `10` / `60` | for "stall": after how many minutes to send, random within the range |
| `MEDIA_MAX_PHOTO` / `_VIDEO` / `_VOICE` / `_ROUND` | `60` | how many files of each kind the model is shown (a separate limit per kind). The list goes into every prompt: the longer it is, the slower the reply and the more mix-ups. `0` — no limit; the extra ones are the last alphabetically, and the bot says so in the log |

```
MEDIA_SEND=all            # everything
MEDIA_SEND=photo,voice    # only photos and voice messages
MEDIA_SEND=               # off
```

### Where to put files

```
media/
├── media.toml        file descriptions (what's on them)
├── photo/            photos: .jpg .png .webp
│   └── later/        photos to stall on
├── video/            videos: .mp4 .mov .webm .mkv
│   └── later/
├── voice/            voice: .ogg/.opus as is; .mp3 .m4a .wav get converted
│   └── later/
└── round/            video messages: any video, cropped to a 384×384 square, up to 60 s
    └── later/
```

The `media/` folder is in `.gitignore` — your files won't get into the repository.

### Descriptions: `media/media.toml`

The bot **doesn't look at the files itself** — it knows only what's written
in `media/media.toml`, and if there's no entry there — what the **file name** says (see below). Based on these descriptions the model decides what fits the conversation.
The full commented template is `media.example.toml`.

```toml
[[media]]
file  = "photo/cat.jpg"                  # path from the media/ folder (or just the file name)
about = "my ginger cat sleeping on the windowsill"
when  = "now"                            # may be sent right away

[[media]]
file  = "photo/later/selfie.jpg"
about = "my mirror selfie in a black hoodie"
when  = "later"                          # stall
delay = [20, 90]                         # send after 20–90 minutes

[[media]]
file  = "voice/bus.ogg"
about = "I say: 'hi, I'm on the bus, can't text'"   # for voice — word for word
when  = "now"

[[media]]
file  = "round/old.mp4"
about = "an old video message"
when  = "never"                          # don't send
```

| Field | Meaning |
|---|---|
| `file` | path to the file from `media/` or just the file name (required) |
| `about` | what's in the photo/video or what you say in the voice/video message. Without it the bot goes by the file name |
| `when` | `now` — right away when asked or when it fits (default); `later` — stall; `never` — don't send |
| `delay` | for `later`: `[min, max]` minutes until sending (otherwise `MEDIA_LATER_MIN/MAX`) |
| `lang` | media language: `ru`, `en`, `uk`… English media goes only to people who write in English, the rest only to people who don't; without `lang` — to everyone |

**Without an entry in `media.toml` the bot understands a file by its name.** So name files after what's in them:
a voice message — by the words you say (`voice/how are you.mp3`, `voice/reading a book, wbu.mp3`), photos and
videos — by what's on them (`photo/cat sleeping on the windowsill.jpg`). The model sees e.g.
`говорю: «reading a book, wbu»` ("I say: …"); `_` in the name counts as a space. `when` = `now`
(or `later` if the file is in a `later/` subfolder). The language of a voice/video message without an entry is taken
from the letters of its name: Cyrillic — `ru`, Latin — `en`; photos and videos fit everyone.
When someone asks for media ("record a voice message about the movie"), the bot looks for the words of the request
in the descriptions and points the model to the best matches — so put **what the file is about** in the name/`about`
("telling the plot of the movie The Purge"), not just its first words.
An entry in `media.toml` always wins over the name — write one when the name can't hold everything
(or you need `when`, `delay`, `lang`).

The bot never listens to or looks at your own media: neither whisper nor vision is applied to them.
Voice messages **from other people** are still transcribed (see "The other person's voice and video messages").

### How it looks

- **Only on request** (`MEDIA_SELF=0`, the default) — the bot never offers anything itself. The request
  ("скинь фотку", "запиши гс", "покажи кота", "есть фото?", "send a pic") is checked by the code, not
  only by the model: without a request no media goes out, even if the model decides to send. And only
  the requested kind goes out: they ask for a voice message — no photo is sent.
- **Right away** (`now`) — sends on the first request (with `MEDIA_SELF=1` — also on its own when it fits).
- **Stall** (`later`) — on the first request it makes an excuse ("can't right now", "I'll send it later");
  if asked again, it agrees and the file goes out by itself after `delay` minutes.
- **Voice messages** — before sending, the other person sees "recording audio" for as long as the
  recording lasts; the message has a waveform, like a real voice message. If voice is enabled, the bot can
  answer "send a voice message" with a suitable ready-made one.
- **Video messages** — "recording video" is shown before sending.
- The same media is never sent to the same chat twice; at most one media per reply.
- Delayed sends (`later`) are lost on bot restart; they aren't sent while paused or in a muted
  chat, nor in the anonymous chat if the partner has already changed.
- Every send is copied to Saved Messages (if `NOTIFY=1`).

Requires `ffmpeg` (as does voice recognition).

---

## How it works

```
message → filters (whitelist / anonymous bot, age, pause)
        → wait a "human" pause, collect the chat history
        → prompt: rules + persona.md + hints for the latest message
        → model → post-processing (dashes, emoji, periods, "I see, ...")
        → checks: empty / dry / repeat → ask the model again
        → "typing…" → send as one or two messages
```

What turned out to matter for natural conversation:
- **Real `system/user/assistant` roles** instead of one wall of text — the model doesn't write the dialog "for both sides".
- **A hint about the specific message** ("they wrote 'д' — that's a girl") works better than a general rule in the prompt.
- **Important things are checked by code**, not by the prompt: age, repeats, empty replies.
- **Post-processing** is cheaper and more reliable than persuading the model not to use periods.

The conversation rules are the `rules` key in `personality.toml` — adjust them to taste.

---

## Safety and responsibility

- **This is a userbot** — automation of a regular account. Telegram may restrict or ban an account for automated messages, especially to strangers. Use at your own risk; better start with a separate account.
- **Who is replying.** The bot doesn't bring up AI on its own, but a direct "are you a bot?" gets an honest answer: an AI assistant is replying for you right now. If you want to warn people up front, set `DISCLOSURE_TEXT` (private chats) and/or `ANON_DISCLOSURE_TEXT`.
- **Minors.** In anonymous mode the model no longer ends the dialog by itself based on the other person's age: there is no age filter.
- **Prompt injection.** The other person's text goes into the prompt. The model only gets text and can't run anything; the `dsh` engine runs `read-only`. Don't give the model tools.
- **Privacy.** With a cloud model the whole conversation goes to the provider. With a local one it goes nowhere.
- The bot doesn't arrange meetings or money, doesn't give out contacts and doesn't promise anything on your behalf — but these are rules for the model, not a guarantee. Read the notifications in Saved Messages.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Заполни TG_API_ID и TG_API_HASH` (fill in the API keys) | step 1: keys from my.telegram.org in `.env` |
| `белый список пуст — отвечать некому` (whitelist empty) | fill in `ALLOW_USERS`, `ALLOW_NON_CONTACTS=1` or `ANON_BOT` |
| `userbot … уже запущен` (already running) | a second instance: `systemctl --user stop userbot` or close the other terminal |
| `нет аккаунта «…»` (no such account) | log in first: `login.py -a <name> …` or `qr_login.py -a <name>` |
| `PERSONA=…: нет папки personas/…` | create `personas/<name>/` or fix `PERSONA` in the account's `.env` |
| `database is locked` | the bot and `send.py`/`login.py` run at the same time; the bot tries to recover the session itself |
| `LLM HTTP 401` | wrong or empty `LLM_API_KEY` |
| `LLM HTTP 400` with a cloud API | `ENGINE=llamacpp` is set → use `ENGINE=openai` |
| `Connection refused` | the model server isn't running or is still loading; check `curl $LLM_URL/models` |
| The bot replies too slowly | heavy model or thinking enabled: `LLM_THINK=0`, a smaller model; with several accounts — they wait in the `LLM_PARALLEL` queue |
| The bot is silent in a chat | you wrote yourself recently (`TAKEOVER_MINUTES`), hourly limit, or the person isn't whitelisted; check the log |
| The bot makes up what's in a photo | `LLM_VISION=0` or a model without vision — the photo doesn't reach it |
| Replies sound robotic | a bigger model; add details, stories and examples of your messages to `persona.md` |

---

## Files

| File | What it is |
|---|---|
| `userbot.py` | the bot itself |
| `ub`, `ub.py` | control a running bot from another terminal: `./ub` |
| `.env.example` | settings template → copy to `.env` |
| `persona.example.md` | template for describing yourself → copy to `persona.md` |
| `personality.example.toml` | template of the bot's behaviour and phrases → copy to `personality.toml` |
| `login.py`, `qr_login.py` | log in without interactive input / via QR |
| `send.py` | send one message as yourself: `send.py @user "text"` |
| `inspect_anon.py` | debugging: latest messages of the anonymous bot with markers |
| `userbot.service` | systemd service for autostart |
| `userbot@.service` | the same, one service per account: `userbot@main`, `userbot@work` |
| `accounts.py` | where each account's files live (`--account <name>`) |
| `accounts/<name>/` | additional accounts: own `.env` (differences), `state/`, optionally own personality (in `.gitignore`) |
| `personas/<name>/` | named personalities (`persona.md`, `personality.toml`, `media/`) for `PERSONA=<name>` (in `.gitignore`) |
| `run.sh` | start with auto-restart and the `ub` console |
| `state/` | session, state, lock, memory about people (created automatically, in `.gitignore`) |
| `files/` | files the bot may send (`FILES_DIR`) |
| `media.example.toml` | template for describing your photos/videos/voice/video messages → `media/media.toml` |
| `README.ru.md` | this documentation in Russian |

---

## License

[MIT](LICENSE)
