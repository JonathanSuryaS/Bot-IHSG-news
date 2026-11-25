# Status — 25 Nov 2026

Short version. Details: [plan.md](plan.md), [hermes-basics.md](hermes-basics.md).

## What works

| Feature | How you use it | Model |
|---|---|---|
| Morning brief | arrives by itself, weekdays 07:30 WIB | hy4-flash:free |
| Price alerts | arrive by themselves every 15 min in market hours, only when something moves | none (free) |
| Stock analysis | `/analysis weekly BBCA` · `/analysis monthly TLKM` | deepseek-v4.1-flash |
| Watchlist | `/watch list` · `/watch add BMRI` · `/watch remove ASII` | hy4-flash:free |
| Alert settings | `/alert show` · `/alert set TLKM move 2` · `/alert off ASII` | hy4-flash:free |

To change a model:
- chat (`/watch`, `/alert`, ...): `hermes config set model.default <model>` then `hermes gateway restart`
- morning brief: `hermes cron edit ihsg-morning --model <model>`
- analysis: edit `config/llm.yaml` → `models.analysis`

## Try first (in this order)

1. On Telegram: `/watch list` and `/alert show` (quick, free)
2. On Telegram: `/analysis weekly BBCA` (report arrives in ~30 seconds)
3. Tomorrow 07:30: check the morning brief arrives, with the new 🌏 global section
4. Tomorrow during market hours: see if alerts are too many or too few, then adjust with `/alert set`

## Before tomorrow morning

- [ ] Commit the new work (see below)
- [ ] Keep the Mac awake: `sudo pmset repeat wakeorpoweron MTWRF 07:20:00`, plugged in
- [ ] Gateway must be running (after a reboot: `hermes gateway`)

## Next (pick later, one at a time)

1. Closing report at 16:45: compares the close with the morning (DeepSeek)
2. Read briefs for a week and tune the prompts
3. Move to a VPS so the Mac can be off
4. Later: RAG over annual reports, web app

## If something breaks

- Bot silent: `hermes gateway status`, then `tail -30 ~/.hermes/logs/gateway.log`
- "No fresh data today": run `uv run brief-check-day` and `uv run brief-fetch` in the repo
- Analysis failed: `tail -20 data/report.log`
- Alerts: `tail -20 ~/.hermes/logs/ihsg-alerts.log`
