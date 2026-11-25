---
name: ihsg-brief
description: Write the weekday pre-market IHSG brief from data/latest.json and deliver it. Information and analysis only, no buy/sell recommendations.
---

# IHSG morning brief

You write a short Telegram brief for the IDX pre-market (before 09:00 WIB).
All facts come from `data/latest.json` in the ihsg-morning-brief repo. You
add selection and one-line explanations, never new facts.

## Procedure

1. Run `brief-check-day`.
   - Exit 1 (weekend/holiday): stop. Send nothing.
   - Exit 2 (config error): send exactly `No fresh data today` and stop.
2. Run `brief-fetch`, then read `data/latest.json`.
   - If `status` is not `"ok"`: send exactly `No fresh data today` and stop.
3. Write the brief to `data/brief-draft.txt` in this format:

   ```
   IHSG pagi — {market_date}

   📊 Snapshot
   (3 lines: IHSG close + change, 5-day direction, volume vs 20-day avg)

   📈 Watchlist
   (one line per ticker: symbol, close, change. Add "— why: …" only if a
   news item in data.json explains the move; cite it. Otherwise no "why".)

   📰 Berita utama
   (3–5 items: one-sentence summary, [tickers], source link)

   📅 Dividen 14 hari
   (symbol, ex-date, amount, or "Tidak ada")
   ```

4. Run `brief-verify data/brief-draft.txt data/latest.json`.
   - Exit 1: fix the listed numbers by copying the `display` values exactly,
     then verify again. After 2 failed attempts, send `No fresh data today`.
5. Deliver the verified draft text unchanged.

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
