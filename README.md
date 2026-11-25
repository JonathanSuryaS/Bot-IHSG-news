# ihsg-morning-brief

A short Telegram brief every weekday at 07:30 WIB, before IDX opens: IHSG,
the watchlist, the news that matters and upcoming dividends.
Information only. No buy/sell recommendations.

```
config/*.yaml ─► brief-fetch (Python, no LLM) ─► data/latest.json
                                                     │
          Hermes cron (07:30 WIB, Mon–Fri) ─► skill "ihsg-brief" ─► brief-verify ─► Telegram
```

New to Hermes? Start with [docs/how-hermes-works.md](docs/how-hermes-works.md),
then follow [docs/build-plan.md](docs/build-plan.md).

## Docs

- [docs/hermes-basics.md](docs/hermes-basics.md): how Hermes Agent works, with a command cheat sheet
- [docs/plan.md](docs/plan.md): build phases with checklists

## Setup

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # installs uv
uv sync                                           # creates .venv with Python 3.11+
uv run pytest
```

Link the skill into Hermes (check the skills path after installing Hermes):

```bash
ln -s "$PWD/skills/ihsg-brief" ~/.hermes/skills/ihsg-brief
```

## Commands

| Command | What it does |
|---|---|
| `uv run brief-check-day` | exit 0 trading day / 1 closed / 2 config error |
| `uv run brief-fetch` | writes `data/YYYY-MM-DD.json` and `data/latest.json` |
| `uv run brief-verify draft.txt data/latest.json` | fails if the draft has a number not in the data |
| `uv run brief-analyze --period week\|month --stock BBCA` | writes `data/analysis-<period>.json` for the `/analysis` skill |
| `uv run brief-watch list\|add KODE\|remove KODE` | edits `config/watchlist.yaml` (validates codes on Yahoo) |
| `uv run brief-alerts show\|set\|on\|off\|add\|remove …` | edits `config/alerts.yaml` |
| `uv run brief-alerts check` | prints alert text or nothing; run every 15 min by cron `ihsg-alerts` |

## Skills

| Telegram command | Model | When |
|---|---|---|
| `/ihsg-brief` | cron job's `--model` (`hy4-flash:free`) | weekdays 07:30 WIB, or on demand |
| `/analysis <weekly\|monthly> <stock>` | started by the chat model; report written by `config/llm.yaml` → `models.analysis` (`deepseek-v4.1-flash`) via `brief-report`, sent with `hermes send` | on demand only |
| `/watch list \| add KODE \| remove KODE` | default chat model (`hy4-flash:free`) | on demand |
| `/alert show \| set KODE move 3 \| set KODE fast 2 \| set KODE volume 2.5 \| on/off KODE \| add/remove KODE` | default chat model (`hy4-flash:free`) | on demand |
| *(automatic alerts)* | none, cron `ihsg-alerts` runs `--no-agent` | every 15 min, 09:00–16:15 WIB, trading days |

## Before first real run

- [ ] Fill `config/idx_holidays_2026.yaml` from the official IDX calendar
- [ ] Test each feed in `config/feeds.yaml`; set `verified: true` on the ones that work
- [ ] Implement the stubs in `src/brief/fetcher.py`
