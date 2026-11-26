---
name: valuasi
description: Educational valuation model (two-stage DCF, or dividend discount model for banks) with a sensitivity table and an Excel file. Command is /valuasi KODE.
---

# /valuasi: valuation model + Excel

This is a thin wrapper around a command. Don't add analysis or commentary.
The command sends the text and the Excel file to Telegram by itself.

1. Map the message: `/valuasi BBRI` (also `/valuation BBRI`) → `BBRI`.
   No code → reply exactly `Format: /valuasi KODE (contoh: /valuasi BBRI)` and stop.
2. Run:
   `cd "/Users/jonathansurya/Documents/GitHub/Bot IHSG news" && ~/.local/bin/uv run -q brief-valuation CODE --send > /dev/null`
3. Exit code 0 → reply exactly `💎 Valuasi terkirim.`
   Exit code 1 → the reason was already sent; reply exactly `Valuasi tidak bisa dibuat untuk saham ini.`
   Other → reply exactly `Gagal membuat valuasi, coba lagi nanti.`
