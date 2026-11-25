---
name: alert
description: Configure intraday IDX price/volume alerts (which stocks, thresholds, on/off). Commands are /alert show, /alert set <kode|IHSG|default> move|volume <angka>, /alert on|off <kode|IHSG>, /alert add|remove <kode>.
---

# /alert: configure price and volume alerts

This is a thin wrapper around a command. Don't add analysis or commentary.
The alerts themselves are sent automatically by a separate no-LLM job every
15 minutes during market hours. This skill only changes the settings.

Repo: `/Users/jonathansurya/Documents/GitHub/Bot IHSG news` (quote the path).
Run commands like this:
`cd "/Users/jonathansurya/Documents/GitHub/Bot IHSG news" && ~/.local/bin/uv run brief-alerts <args>`

## Procedure

1. Map the user's message to arguments:

   | User writes | Arguments |
   |---|---|
   | `/alert` or `/alert show` | `show` |
   | `/alert set TLKM move 2` | `set TLKM move 2` (alert at ±2%) |
   | `/alert set BBCA volume 3` | `set BBCA volume 3` (alert at 3× average volume) |
   | `/alert set TLKM fast 1.5` | `set TLKM fast 1.5` (sudden move: ±1,5% within ~15 minutes) |
   | `/alert set IHSG fast 0.8` | `set IHSG fast 0.8` |
   | `/alert set default move 4` | `set default move 4` (all stocks without their own setting) |
   | `/alert set IHSG move 1` | `set IHSG move 1` |
   | `/alert off ASII` / `/alert on ASII` (also "matikan"/"nyalakan") | `off ASII` / `on ASII` |
   | `/alert add GOTO` | `add GOTO` (alert-only stock, not in the watchlist) |
   | `/alert remove GOTO` | `remove GOTO` |

   - Accept Indonesian words for the metric: "gerak"/"harga" → `move`,
     "cepat"/"mendadak"/"tiba-tiba" → `fast`, "volume" → `volume`. Accept
     decimals with a comma (`2,5`).
   - Anything you can't map → run `show` and add this line above its output:
     `Format: /alert show | set KODE move 3 | set KODE volume 2.5 | on KODE | off KODE | add KODE | remove KODE`
2. Pass codes exactly as the user typed them; the command validates them.
3. Reply with the command's output, unchanged.
