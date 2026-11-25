# How Hermes works (and how this project uses it)

Hermes Agent (by Nous Research) is a program that runs on your machine and
wraps an LLM in a loop. You give it a request, the LLM decides what to do, it
calls **tools** (run a terminal command, read a file, search the web), looks
at the result, and repeats until the task is done.

Everything else is built around that loop.

## The pieces

| Piece | What it is | Where it lives | Our use |
|---|---|---|---|
| **Model / provider** | The LLM that does the thinking; you bring an API key | `~/.hermes/config.yaml`, keys in `~/.hermes/.env` | Writes the brief |
| **Tools** | What the agent can *do*: terminal, files, web, memory, cron | built in | Runs `brief-fetch`, reads the JSON |
| **Skills** | A `SKILL.md` file: step-by-step instructions for one kind of task. Each skill is also a slash command | `~/.hermes/skills/…` (or `<repo>/.hermes/skills/`) | `ihsg-brief`: how to write the brief |
| **Gateway** | Background process that connects Hermes to chat apps | `hermes gateway` | Telegram |
| **Cron** | Scheduler inside the gateway: at set times it starts the agent with a prompt and skills, then sends the result somewhere | `hermes cron …` | 07:30 weekdays, sent to Telegram |
| **Memory** | Notes the agent keeps between sessions | `~/.hermes/` | Not needed here |

Things worth knowing:

- **Cron runs inside the gateway.** No running gateway means no brief. The
  gateway checks the schedule every 60 seconds. If the Mac is asleep or the
  gateway is stopped at 07:30, that morning is skipped.
- **Skills are slash commands.** Type `/ihsg-brief` in the CLI or Telegram to
  test the skill at any time, without waiting for the schedule.
- **Terminal commands need approval.** By default Hermes auto-approves
  low-risk commands, blocks dangerous ones, and asks about anything
  uncertain. The local terminal has the same file access as your user
  account.
- **Config precedence:** CLI arguments override `config.yaml`, which
  overrides `.env`, which overrides built-in defaults.

## What happens at 07:30

```
07:30 WIB  gateway's scheduler fires the job
   │
   ├─ starts the agent with the "ihsg-brief" skill loaded
   │
   ├─ agent runs:  brief-check-day   → holiday? stop. config error? "No fresh data today"
   ├─ agent runs:  brief-fetch       → Python gets yfinance + RSS → data/latest.json
   │                                   status not "ok"? "No fresh data today"
   ├─ agent reads the JSON, writes the draft   ← the only step where the LLM is creative
   ├─ agent runs:  brief-verify      → any number not in the data? fix it or give up
   │
   └─ the agent's final message is sent to Telegram
```

## Who does what

- **Python handles facts.** Prices, dates and news links are fetched by code,
  which is predictable and testable.
- **The LLM handles judgment.** It picks which news matters, explains movers
  in one line, and writes readable prose.
- **Python checks the LLM.** `verify.py` catches any number the model made up
  before the brief is sent.

That's why most of this repo is plain Python. Hermes only appears in the
skill file (`skills/ihsg-brief/SKILL.md`) and the cron job.

## Command cheat sheet

```bash
hermes                      # chat in the terminal
hermes setup                # setup wizard (provider, API key)
hermes model                # change provider/model
hermes gateway setup        # connect Telegram
hermes gateway              # run the gateway in the foreground
hermes gateway install      # install it as a background service
hermes skills browse        # see available skills
hermes cron list            # list scheduled jobs
hermes cron run <name>      # fire a job on the next tick (gateway must be running)
hermes cron runs <name>     # see past runs
```

## Sources

- [Hermes Agent docs](https://hermes-agent.nousresearch.com/docs)
- [Docs index (llms.txt)](https://hermes-agent.nousresearch.com/docs/llms.txt)
- Pages used: Installation, Quickstart, Skills, Cron, Telegram, Configuration,
  Tools, Security

Checked against the docs on 2026-11-25. Hermes changes quickly, so re-check
commands against the docs if something doesn't match.
