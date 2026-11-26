---
name: ihsg-brief
description: Write the weekday pre-market IHSG brief from data/latest.json and deliver it. Information and analysis only, no buy/sell recommendations.
---

# IHSG morning brief

You write a short Telegram brief for the IDX pre-market (before 09:00 WIB).
All facts come from `data/latest.json` in the ihsg-morning-brief repo. You
add selection and one-line explanations, never new facts.

## Where things are

- Repo: `/Users/jonathansurya/Documents/GitHub/Bot IHSG news` (the path has
  spaces, so always quote it).
- Run project commands exactly like this, from the repo:
  `cd "/Users/jonathansurya/Documents/GitHub/Bot IHSG news" && ~/.local/bin/uv run <command>`
- Data: `data/latest.json`. Draft: `data/brief-draft.txt` (both inside the repo).

## Procedure

1. Run `brief-check-day` and look at its exit code.
   - Exit 0: trading day, continue.
   - Exit 1 (weekend/holiday): reply with exactly `Bursa libur hari ini.` and stop.
   - Exit 2 (config error): reply with exactly `No fresh data today` and stop.
2. Run `brief-fetch`, then read `data/latest.json`.
   - If `status` is not `"ok"`: reply with exactly `No fresh data today` and stop.
3. Write the brief to `data/brief-draft.txt` in this format:

   ```
   IHSG pagi — {market_date}

   📊 Penutupan kemarin
   (3 lines: IHSG close yesterday + change, 5-day direction, volume vs 20-day avg)

   🌏 Global semalam
   (from `global`, grouped on 3 short lines, name + change_pct, e.g.
   "AS: Dow +0,30% · S&P 500 -0,10% · Nasdaq +0,25%"
   "Asia: Nikkei … · Hang Seng … · STI …"
   "USD/IDR {close} ({change_pct}) · Brent … · Emas … · CPO …"
   Skip any market missing from `global`.)

   📈 Watchlist (penutupan kemarin)
   (one line per ticker: symbol, close, change. Add "— why: …" only if a
   news item in data.json explains the move; cite it. Otherwise no "why".)

   📰 Berita pasar
   (3–5 items from category "market": one-sentence summary, [tickers], link.
   Prefer items with watchlist tickers, then items that move the whole index.)

   🏛 Ekonomi
   (2–3 items from category "economy": rupiah, BI rate, inflation, fiscal
   policy, regulation (OJK/IDX), commodities, big government decisions.
   Skip lifestyle, HR/civil-service, and promo/CSR stories.)

   📅 Dividen 14 hari
   (symbol, ex-date, amount; if amount is null write "nilai belum diumumkan";
   if the list is empty write "Tidak ada")
   ```

   Field notes:
   - `index.display.volume_vs_20d` can be null. Then leave volume out of the
     snapshot; don't say "volume normal".
   - If `errors` names a watchlist ticker, write "data tidak tersedia" for it.
     Ignore other errors (feeds, holidays): they're for the developer.
   - Many news items repeat the same story from different sources. Pick one.

4. Run `brief-verify data/brief-draft.txt data/latest.json`.
   - Exit 1: fix the listed numbers by copying the `display` values exactly,
     then verify again. After 2 failed attempts, send `No fresh data today`.
5. Reply with the verified draft text, unchanged, as your whole final answer.
   No preamble ("Here is the brief"), no closing remarks.

## Hard rules

- Copy every number from a `display` field, character for character. Never
  compute, round, convert or estimate a number.
- Never write buy, sell, hold, accumulate, target price, entry, exit, cut
  loss, "layak dibeli", "saatnya jual", or any recommendation or price
  prediction. Describe what happened, not what to do.
- Every news item must include its `url` from data.json. No news without a link.
- A "why" must point to a specific news item. If nothing explains a move,
  leave the "why" out.
- Keep it short. The whole brief should be readable in under a minute.
