---
name: fundamental
description: Multi-year financial statements and trends (revenue, profit, margin, ROE, debt, cash flow, dividends) for an IDX stock. Command is /fundamental KODE.
---

# /fundamental: multi-year financials

This is a thin wrapper around a command. Don't add analysis or commentary.

1. Map the message: `/fundamental BBRI` → `BBRI`. Several codes → run once per
   code. No code → reply exactly `Format: /fundamental KODE (contoh: /fundamental BBRI)`.
2. Run:
   `cd "/Users/jonathansurya/Documents/GitHub/Bot IHSG news" && ~/.local/bin/uv run -q brief-fundamental CODE`
3. Reply with the command's output, unchanged (join several with a blank line).
