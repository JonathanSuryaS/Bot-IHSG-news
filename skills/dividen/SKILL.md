---
name: dividen
description: Dividend history, trend and yield for an IDX stock, optionally yield on cost for a buy price. Commands are /dividen KODE and /dividen KODE HARGA_BELI.
---

# /dividen: dividend summary

This is a thin wrapper around a command. Don't add analysis or commentary.

Repo: `/Users/jonathansurya/Documents/GitHub/Bot IHSG news` (quote the path).
Run it like this:
`cd "/Users/jonathansurya/Documents/GitHub/Bot IHSG news" && ~/.local/bin/uv run -q brief-dividend <args>`

## Procedure

1. Map the user's message to arguments:
   - `/dividen BBRI` → `BBRI`
   - `/dividen BBRI 3800` (also `3.800`, `Rp3.800`) → `BBRI 3800`
   - Several codes (`/dividen BBRI TLKM`, no price) → run once per code.
   - No code → reply exactly:
     `Format: /dividen KODE atau /dividen KODE HARGA_BELI (contoh: /dividen BBRI 3800)`
2. Pass the code and price exactly as the user typed them. Don't compute or
   change any number.
3. Reply with the command's output, unchanged (join several outputs with a
   blank line). No preamble, no extra advice.
