---
name: watch
description: Manage the IDX watchlist used by the daily brief and /analysis. Commands are /watch list, /watch add <kode>, /watch remove <kode>.
---

# /watch: manage the watchlist

This is a thin wrapper around a command. Don't add analysis or commentary.

Repo: `/Users/jonathansurya/Documents/GitHub/Bot IHSG news` (quote the path).
Run commands like this:
`cd "/Users/jonathansurya/Documents/GitHub/Bot IHSG news" && ~/.local/bin/uv run brief-watch <args>`

## Procedure

1. Map the user's message to arguments:
   - `/watch` or `/watch list` → `list`
   - `/watch add BMRI` (also "tambah") → `add BMRI`
   - `/watch remove ASII` (also "hapus", "delete") → `remove ASII`
   - Several codes (`/watch add BMRI GOTO`) → run the command once per code.
   - Anything else → reply exactly:
     `Format: /watch list | /watch add KODE | /watch remove KODE`
2. Pass the code exactly as the user typed it. Don't turn a company name into
   a code yourself: the command rejects anything that isn't a 4-letter code,
   and its error message says so.
3. Reply with the command's output, unchanged. If you ran it several times,
   join the outputs with a newline.

Changes apply from the next daily brief and the next /analysis. Stocks in the
watchlist are also checked by the intraday alerts (see /alert).
