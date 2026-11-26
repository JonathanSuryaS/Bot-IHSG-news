---
name: analysis
description: Start an on-demand weekly or monthly analysis of one IDX stock. Command format is /analysis <weekly|monthly> <stock>. The report is written by a separate script with its own model and sent to Telegram directly; this skill only starts it.
---

# /analysis <weekly|monthly> <stock>

You only start a script. You do not write the analysis yourself, and you do
not wait for it. The script builds the data, has the analysis model (set in
`config/llm.yaml`) write and number-check the report, and sends it to the
user's Telegram on its own.

Repo: `/Users/jonathansurya/Documents/GitHub/Bot IHSG news`.

## Procedure

1. Read the command. Format: `/analysis <period> <stock>`
   - `<period>`: `weekly`/`mingguan` or `monthly`/`bulanan`.
   - `<stock>`: the rest of the message, e.g. `BBCA`, `bmri`, `Telkom`.
   - If the period or stock is missing, or the period is anything else, or the
     stock contains characters other than letters, digits, spaces and dots,
     reply exactly with this and stop:

     ```
     Format: /analysis <weekly|monthly> <kode saham>
     Contoh:
     /analysis weekly BBCA
     /analysis monthly TLKM
     ```

2. Run this one terminal command, with PERIOD and STOCK filled in. Keep the
   double quotes around STOCK. It returns immediately:

   ```
   cd "/Users/jonathansurya/Documents/GitHub/Bot IHSG news" && nohup ~/.local/bin/uv run -q brief-report analysis PERIOD "STOCK" --send >> data/report.log 2>&1 &
   ```

3. Reply exactly (fill in mingguan/bulanan and the stock as typed):
   `⏳ Analisis {mingguan|bulanan} {STOCK} sedang dibuat, dikirim dalam ±1 menit.`

Don't add anything else. The report, or an error message if something goes
wrong, arrives as a separate message.

## If the job exits with code 1

A traceback ending in `http.client.RemoteDisconnected: Remote end closed
connection without response` means the report model's connection dropped.
`chat()` in `src/brief/report.py` doesn't catch that exception type, so there
is no automatic retry and nothing reaches Telegram. The drop is transient:
re-run the exact same command (it can take 2-4 tries), then check
`ls -lt data | head -3` for a fresh `data/analysis-report.txt` to confirm the
report was written and sent. If it keeps failing, test the same payload
directly against `https://router.nibie.app/v1/chat/completions` using the key
in `~/.hermes/.env` (`HERMES_CUSTOM_ROUTER_NIBIE_APP_*_API_KEY`); if that
succeeds, the router is flaky rather than the code or the data.
