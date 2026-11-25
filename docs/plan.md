# Build plan

Goal: every weekday at 07:30 WIB, a short Telegram brief covering IHSG, the
watchlist, the news that matters and upcoming dividends. Information only,
no buy/sell recommendations. No RAG for now. See
[hermes-basics.md](hermes-basics.md) for how Hermes itself works.

## Who does what

- **Python handles facts.** Prices, dates and news links are fetched by code,
  which is predictable and testable (`src/brief/`).
- **The LLM handles judgment.** It picks which news matters, explains movers
  in one line and writes readable prose (`skills/ihsg-brief/SKILL.md`).
- **Python checks the LLM.** `brief-verify` fails if any number in the brief
  isn't in `data.json`.

## What happens at 07:30

```
07:30 WIB  gateway's scheduler fires the job
   │
   ├─ starts the agent with the "ihsg-brief" skill loaded
   │
   ├─ brief-check-day  → holiday/weekend: stop. config error: "No fresh data today"
   ├─ brief-fetch      → yfinance + RSS → data/latest.json
   │                     status not "ok": "No fresh data today"
   ├─ agent reads the JSON and writes the draft   ← only creative step
   ├─ brief-verify     → numbers not in data: fix, or give up after 2 tries
   │
   └─ the agent's final message is delivered to Telegram
```

## Phases

Each phase has a "done when" check, so you know when to move on.

### Phase 0: Install Hermes and get to know it
- [x] Install (done 2026-11-25: v0.23.4, without browser/computer-use), then `source ~/.zshrc`
- [ ] `hermes setup` → own API key
- [ ] Chat with `hermes`: ask it to list this repo's files, try `/skills`,
      and notice when it asks permission before running a command

**Done when:** it answers in the terminal and runs a command like `ls`.

### Phase 1: Connect Telegram
- [ ] Create the bot with @BotFather and get your user ID from @userinfobot
- [ ] `hermes gateway setup` → Telegram, with `TELEGRAM_ALLOWED_USERS` set
- [ ] `hermes gateway`, message the bot, then send `/sethome`

**Done when:** the bot replies to you on Telegram.

### Phase 2: Fetcher (plain Python, no Hermes)
- [x] uv + `.venv` (Python 3.12) via `uv sync`; `uv run pytest` passes
- [x] Implement `src/brief/fetcher.py` (the schema is in its docstring)
- [x] Test feeds: 11 work (4 market, 7 economy); Bisnis.com blocks bots (403)
- [ ] Fill `config/idx_holidays_2026.yaml` from the official IDX calendar
- [ ] Compare one day's numbers in `data/latest.json` against a real quote page
- [ ] Known gap: Yahoo gives upcoming ex-dates but not amounts (shown as
      "nilai belum diumumkan"); a KSEI/IDX source can fix this later

**Done when:** `uv run brief-fetch` writes a `data/latest.json` whose numbers
match a real quote page.

### Phase 3: Skill, run by hand
- [ ] Make the skill visible to Hermes, using one of:
  - `ln -s "$PWD/skills/ihsg-brief" ~/.hermes/skills/ihsg-brief`, or
  - move it to `.hermes/skills/ihsg-brief/`, then run `hermes skills trust`
- [ ] Run `/ihsg-brief` in the CLI, then on Telegram

**Done when:** the brief looks right and `brief-verify` passes.

### Phase 4: Cron
```bash
hermes cron create "30 7 * * 1-5" "Write and deliver today's IHSG brief" \
  --skill ihsg-brief --name ihsg-morning \
  --timezone Asia/Jakarta --workdir "<repo path>" --deliver telegram
hermes cron run ihsg-morning      # fire once now to test
```
- [ ] `hermes gateway install` so the gateway restarts on its own
- [ ] Keep the Mac awake at 07:30, e.g.
      `sudo pmset repeat wakeorpoweron MTWRF 07:20:00`
      (or move to a small always-on server later)

**Done when:** a brief arrives without you doing anything.

### Phase 4b: Move to the cloud (optional, after Phase 4 works locally)
The gateway must run all the time for cron to fire, so the Mac-free option
is an always-on machine.

| Option | Cost | Verdict |
|---|---|---|
| Small VPS (Hetzner / DigitalOcean / Vultr / Lightsail), 1–2 GB RAM, Singapore region | ~$4–6/mo | Recommended |
| Oracle Cloud Always Free | $0 | Works; signup can be difficult and idle instances may be reclaimed |
| Google Cloud e2-micro free tier | $0 | 1 GB RAM, US regions only; tight |
| GitHub Actions / serverless | $0 | Doesn't fit: Hermes's gateway needs to run continuously |

- [ ] Create the VPS and lock SSH to key-only login (no inbound ports needed)
- [ ] `git clone`, install uv, `uv sync`
- [ ] Run `uv run brief-fetch` there early: Yahoo may treat data-center IPs differently
- [ ] Install Hermes, then run `hermes setup` and `hermes gateway setup` again
      (re-enter keys; don't copy `.env` files around)
- [ ] `sudo hermes gateway install --system` (starts on boot)
- [ ] Recreate the skill and cron job (`--timezone Asia/Jakarta` already
      makes the server's timezone irrelevant)
- [ ] Stop the gateway on the Mac. One bot token = one running gateway,
      otherwise you get duplicate briefs

**Done when:** a brief arrives with the Mac closed.

### Phase 5: Tune for a week
- [ ] Read each morning's brief and adjust the wording in `SKILL.md` only
- [ ] Note any recurring `brief-verify` failures; they usually mean
      `fetcher.py` needs another `display` field

## Hard rules (also in SKILL.md)

- Every number comes from `data.json`, never from the LLM, and `brief-verify` enforces it.
- Fetch failure or stale data → send exactly "No fresh data today".
- Skip IDX holidays and weekends.
- No buy/sell/hold/target-price language.

## Later (not now)

- Keep the daily `data/YYYY-MM-DD.json` files. They're already saved and
  could become a dataset.
- RAG over IDX annual reports, then a full-stack app.
