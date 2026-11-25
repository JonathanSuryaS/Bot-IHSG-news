# Build plan

Goal: every weekday at 07:30 WIB, a short Telegram brief with IHSG, the
watchlist, the news that matters and the dividend calendar.
Information and analysis only. No buy/sell recommendations.
Out of scope for now: RAG, storing data for analysis, a web app.

Each phase has a "done when" check. Don't move on until it passes.

## Phase 0: Install Hermes and get to know it

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.zshrc
hermes setup        # choose "own API key", paste your LLM key
hermes              # chat with it in the terminal
```

The installer sets up its own Python, separate from this project's.

Try: ask it to list the files in this repo, type `/skills` to see the skills
that come with it, and notice when it asks permission before running a command.

**Done when:** it answers in the terminal and runs a command like `ls`.

## Phase 1: Connect Telegram

1. Message @BotFather, send `/newbot`, and copy the token it gives you. Keep the
   token secret; `/revoke` in BotFather replaces it.
2. Get your numeric user ID from @userinfobot.
3. Run `hermes gateway setup`, choose Telegram, and enter the token and your user ID.
   This sets `TELEGRAM_ALLOWED_USERS`, so only you can talk to the agent.
4. Run `hermes gateway`, then message the bot.

**Done when:** the bot replies to you on Telegram.

## Phase 2: Fetcher (Python only, no Hermes)

- Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`, then `uv sync`
- Fill in the stubs in `src/brief/fetcher.py`
- Test each feed in `config/feeds.yaml` and set `verified: true` on the ones that work
- Fill in `config/idx_holidays_2026.yaml` from the official IDX calendar

**Done when:** `uv run brief-fetch` writes `data/latest.json` and its numbers
match a real quote page.

## Phase 3: Skill, run by hand

Make the skill visible to Hermes, using one of:

```bash
# Option A: symlink into Hermes's skills folder
ln -s "$PWD/skills/ihsg-brief" ~/.hermes/skills/ihsg-brief

# Option B: keep it in the repo as a project skill
mkdir -p .hermes && git mv skills .hermes/skills && hermes skills trust
```

Then type `/ihsg-brief` in the CLI or Telegram and read the output.

**Done when:** the brief looks right and `brief-verify` passes on it.

## Phase 4: Cron

```bash
hermes cron create "30 7 * * 1-5" "Write and deliver today's IHSG brief" \
  --skill ihsg-brief --name ihsg-morning \
  --timezone Asia/Jakarta \
  --workdir "/Users/jonathansurya/Documents/GitHub/Bot IHSG news" \
  --deliver telegram

hermes cron run ihsg-morning      # fire once now to test
hermes gateway install            # keep the gateway running in the background
```

Cron only runs while the gateway is running, so keep the Mac awake at 07:30:

```bash
sudo pmset repeat wakeorpoweron MTWRF 07:20:00
```

Later option: move it to a small always-on server.

**Done when:** a brief arrives on Telegram without you doing anything.

## Phase 5: Tune for a week

Read each morning's brief and adjust only the wording in `SKILL.md`
(format, length, what counts as a "mover"). Use `hermes cron runs ihsg-morning`
to see what happened on a given day.

**Done when:** you'd read it every morning without wanting to change anything.

## Hard rules (all phases)

- Every number in the brief comes from `data.json`; `brief-verify` enforces this.
- Fetch failure or stale data means the bot sends exactly "No fresh data today".
- IDX holidays and weekends are skipped.
- No buy/sell/target-price language.

## Status

- [x] Repo scaffold, holiday check, number verifier, tests
- [ ] Phase 0: Install Hermes
- [ ] Phase 1: Telegram
- [ ] Phase 2: Fetcher
- [ ] Phase 3: Skill
- [ ] Phase 4: Cron
- [ ] Phase 5: Tuning
