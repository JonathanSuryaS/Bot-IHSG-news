# How Hermes Agent works

Notes for this project, based on the official docs
(<https://hermes-agent.nousresearch.com/docs>). Hermes changes fast, so check
the docs if a command here stops working.

## The core idea

Hermes runs an LLM in a loop on your machine. You give it a request, the LLM
decides what to do, it uses **tools** (run a terminal command, read a file,
search the web), looks at the result and repeats until the task is done.
Everything else is built around that loop.

## The pieces

| Piece | What it is | Where it lives | Our use |
|---|---|---|---|
| **Model / provider** | The LLM that does the thinking. You bring an API key. | `~/.hermes/config.yaml`, keys in `~/.hermes/.env` | Writes the brief |
| **Tools** | What the agent can *do*: terminal, files, web, memory, cron | built in | Runs `brief-fetch`, reads the JSON |
| **Skills** | A `SKILL.md` file: step-by-step instructions the agent loads for one kind of task. Each skill also becomes a slash command. | `~/.hermes/skills/…` | `ihsg-brief` = how to write the brief |
| **Gateway** | Background process that connects Hermes to chat apps | `hermes gateway` | Telegram |
| **Cron** | Scheduler inside the gateway. It starts the agent with a prompt and skills at set times, then delivers the result. | `hermes cron …` | 07:30 weekdays → Telegram |
| **Memory** | Notes the agent keeps between sessions | `~/.hermes/` | Not needed here |

### Things that matter for this project

- **Cron only runs while the gateway is running.** The gateway checks the
  schedule every 60 seconds. If the Mac is asleep or the gateway is stopped
  at 07:30, that morning's brief is skipped.
- **Skills are slash commands.** Type `/ihsg-brief` in the CLI or on Telegram
  to test the skill anytime, without waiting for the schedule.
- **Skill locations.** Global skills live in `~/.hermes/skills/`. A repo can
  have its own in `<repo>/.hermes/skills/`, but you have to run
  `hermes skills trust` before Hermes loads them.
- **Terminal approvals.** By default (`approvals.mode: smart`) Hermes
  auto-approves low-risk commands and asks before risky ones. Cron jobs deny
  dangerous commands by default. The local backend has the same file access
  as your user account.
- **Secrets.** `hermes config set SOME_API_KEY ...` stores the value in
  `~/.hermes/.env`. Other settings go in `~/.hermes/config.yaml`.

## Command cheat sheet

```bash
# install (macOS / Linux / WSL2); the installer sets up its own Python
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.zshrc

hermes setup                # first-run wizard: provider + API key
hermes model                # switch provider/model
hermes                      # chat in the terminal
hermes tools                # enable/disable toolsets

hermes gateway setup        # connect Telegram (bot token + allowed user IDs)
hermes gateway              # run gateway in foreground
hermes gateway install      # install as a background service

hermes skills browse | search <kw> | install <src> | trust

hermes cron create "<schedule>" "<prompt>" --skill <name> \
  --timezone Asia/Jakarta --workdir <path> --deliver telegram --name <name>
hermes cron list | run <name> | pause <name> | runs <name> | remove <name>
```

Schedules accept cron syntax (`30 7 * * 1-5`) or plain phrases like
`weekdays at 9am`.

## Telegram setup

1. Message **@BotFather**, send `/newbot`, pick a name and a username ending
   in `bot`. Copy the token and keep it secret (`/revoke` rotates it).
2. Get your numeric user ID from **@userinfobot**.
3. Run `hermes gateway setup`, choose Telegram, and enter the token and your
   user ID. Or add them to `~/.hermes/.env` yourself:
   ```
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_ALLOWED_USERS=<your numeric id>
   ```
   Always set `TELEGRAM_ALLOWED_USERS` so that only you can control your agent.
4. Run `hermes gateway` and message your bot.
5. In the chat, send `/sethome` so cron's `--deliver telegram` knows which
   chat to send to.

## Sources

- [Docs home](https://hermes-agent.nousresearch.com/docs)
- [Docs index (llms.txt)](https://hermes-agent.nousresearch.com/docs/llms.txt)
- Pages used: getting-started/installation, getting-started/quickstart,
  user-guide/features/skills, user-guide/features/cron,
  user-guide/messaging/telegram, user-guide/configuration,
  user-guide/features/tools, user-guide/security
