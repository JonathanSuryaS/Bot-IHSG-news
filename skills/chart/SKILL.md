---
name: chart
description: Candlestick chart image plus technical summary (moving averages, RSI, MACD, support/resistance, candle pattern) for an IDX stock or IHSG. Commands are /chart KODE and /chart KODE weekly.
---

# /chart: candlestick chart + technical summary

This is a thin wrapper around a command. Don't add analysis or commentary.
The command sends the image and the text to Telegram by itself.

Repo: `/Users/jonathansurya/Documents/GitHub/Bot IHSG news` (quote the path).

## Procedure

1. Map the user's message to arguments:
   - `/chart BBRI` → `BBRI`
   - `/chart BBRI weekly` (also "mingguan") → `BBRI weekly`
   - `/chart IHSG` → `IHSG`
   - No code → reply exactly:
     `Format: /chart KODE [daily|weekly] (contoh: /chart BBRI, /chart IHSG weekly)`
     and stop.
2. Run, with the arguments in place of ARGS:
   `cd "/Users/jonathansurya/Documents/GitHub/Bot IHSG news" && ~/.local/bin/uv run -q brief-chart ARGS --send > /dev/null`
3. If the exit code is 0, reply exactly `📈 Chart terkirim.`
   Otherwise reply exactly `Gagal membuat chart, coba lagi nanti.`
