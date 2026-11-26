# 📈 IHSG Bot

**Your Indonesian stock market assistant on Telegram.**
A morning brief before the bell, a closing report after it, price alerts in between,
plus on-demand analysis, charts, fundamentals, valuation and dividends for any IDX stock.

> ℹ️ Information and education only. The bot never gives buy/sell recommendations,
> and every number in an LLM-written brief is checked against the source data before it is sent.

Built on [Hermes Agent](https://github.com/NousResearch/hermes-agent) · Python 3.11+ · managed with [uv](https://docs.astral.sh/uv/)

---

## ✨ Features

### 🌅 Arrives by itself

| | When | What you get |
|---|---|---|
| **Morning brief** | Weekdays 07:30 WIB | Yesterday's close, global markets, your watchlist, news that matters, upcoming dividends |
| **Closing report** | Weekdays 16:45 WIB | Today's result, alerts that fired, news |
| **Price & volume alerts** | Every 15 min in market hours | Only when something actually moves |

### 💬 Ask for it

| Command | What it does |
|---|---|
| `/analysis weekly BBCA` | Weekly or monthly analysis with a chart and technical section |
| `/chart BBRI` · `/chart IHSG weekly` | Candlestick chart with MA, RSI, MACD, support/resistance |
| `/fundamental BBRI` | 4 years of financial statements and trends |
| `/valuasi BBRI` | DCF/DDM model, sensitivity table and an Excel file |
| `/dividen BBRI 3800` | Dividend history, trend and yield (optionally from your buy price) |
| `/formula ROE BBRI` | Learn a ratio: meaning, formula, example, and the stock's current value |
| `/watch add BMRI` | Manage your watchlist |
| `/alert set TLKM move 2` | Tune alerts: daily move, fast move, volume spikes |
| `/menu` | Show every command |

Bot replies are in Bahasa Indonesia.

---

## 🧠 How it works

```
config/*.yaml ─► brief-fetch (Python, no LLM) ─► data/latest.json
                                                     │
        Hermes cron (07:30 WIB, Mon–Fri) ─► skill "ihsg-brief" ─► brief-verify ─► Telegram
```

- **Python does the numbers.** Fetching, charts, fundamentals, valuation, dividends and alerts are plain Python, with no LLM and no token cost.
- **The LLM does the writing.** Briefs and analysis reports are written by the model set in `config/llm.yaml`.
- **`brief-verify` checks the facts.** A draft that contains a number not found in the data is rejected.
- **Trading-day aware.** IDX holidays live in `config/idx_holidays_*.yaml`, so nothing runs when the market is closed.

---

## 🚀 Quick start

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # install uv
uv sync                                           # create .venv
uv run pytest                                     # run the tests
```

Link the skills into Hermes:

```bash
for s in skills/*; do ln -s "$PWD/$s" ~/.hermes/skills/$(basename "$s"); done
```

New to Hermes? Read [docs/how-hermes-works.md](docs/how-hermes-works.md), then follow [docs/build-plan.md](docs/build-plan.md).

---

## 🛠 CLI tools

| Command | Purpose |
|---|---|
| `brief-check-day` | Exit 0 on trading days, 1 when closed, 2 on config error |
| `brief-fetch` | Fetch data to `data/latest.json` |
| `brief-verify draft.txt data/latest.json` | Reject drafts with unverified numbers |
| `brief-analyze --period week --stock BBCA` | Data for `/analysis` |
| `brief-report` | Write the analysis report with the LLM |
| `brief-closing` | Build the closing report |
| `brief-alerts check` | Print alerts, if any (run by cron every 15 min) |
| `brief-watch` · `brief-alerts` | Edit the watchlist and alert settings |
| `brief-chart` · `brief-fundamental` · `brief-valuation` · `brief-dividend` · `brief-formula` | Back the matching Telegram commands |

Run any of them with `uv run <command>`.

---

## 📁 Project layout

```
config/    watchlist, alerts, feeds, holidays, LLM models, valuation assumptions, menu text
prompts/   prompts for analysis and closing reports
skills/    Hermes skills, one per Telegram command
src/brief/ the Python package behind every CLI tool
tests/     pytest suite
docs/      status, plan and Hermes guides
```

---

## 📚 Docs

- [docs/STATUS.md](docs/STATUS.md): what works today, troubleshooting
- [docs/how-hermes-works.md](docs/how-hermes-works.md): Hermes in plain words
- [docs/hermes-basics.md](docs/hermes-basics.md): command cheat sheet
- [docs/plan.md](docs/plan.md): build phases and roadmap

## 🗺 Roadmap

- [x] Morning brief, closing report, alerts
- [x] Analysis, charts, fundamentals, valuation, dividends, formulas
- [ ] Tune prompts after a week of real briefs
- [ ] Move to a VPS
- [ ] RAG over annual reports, web app
