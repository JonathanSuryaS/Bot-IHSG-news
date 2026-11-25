# ihsg-morning-brief

A short Telegram brief every weekday at 07:30 WIB, before IDX opens: IHSG,
the watchlist, the news that matters and upcoming dividends.
Information only. No buy/sell recommendations.

```
config/*.yaml ─► brief-fetch (Python, no LLM) ─► data/latest.json
                                                     │
          Hermes cron (07:30 WIB, Mon–Fri) ─► skill "ihsg-brief" ─► brief-verify ─► Telegram
```

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

## Before first real run

- [ ] Fill `config/idx_holidays_2026.yaml` from the official IDX calendar
- [ ] Test each feed in `config/feeds.yaml`; set `verified: true` on the ones that work
- [ ] Implement the stubs in `src/brief/fetcher.py`
