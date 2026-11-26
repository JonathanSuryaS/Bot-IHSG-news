---
name: formula
description: Explain a financial ratio (ROE, P/E, PBV, DER, ...) with its formula, an example and how to read it, optionally with a stock's current value. Commands are /formula, /formula ROE, /formula ROE BBRI.
---

# /formula: explain financial ratios

This is a thin wrapper around a command. Don't add analysis or commentary.

Repo: `/Users/jonathansurya/Documents/GitHub/Bot IHSG news` (quote the path).
Run it like this:
`cd "/Users/jonathansurya/Documents/GitHub/Bot IHSG news" && ~/.local/bin/uv run -q brief-formula <args>`

## Procedure

1. Pass everything after `/formula` as arguments, unchanged:
   - `/formula` → no arguments (shows the list)
   - `/formula ROE` → `ROE`
   - `/formula P/E BBRI` → `P/E BBRI`
   - `/formula payout ratio TLKM` → `payout ratio TLKM`
2. Quote each argument so `P/E` and spaces survive the shell.
3. Reply with the command's output, unchanged. No preamble, no extra
   explanation: the text already contains it.
