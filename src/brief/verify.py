"""Check that every number in the brief appears in data.json.

Usage: brief-verify <brief.txt> <data.json>
Exit 0 = all numbers found, 1 = unverified numbers (printed), 2 = bad input.

How it works: pull numeric tokens out of the brief and out of the raw
data.json text using the same regex, then require brief ⊆ data. A leading
+/- is part of the token (a flipped sign fails); %/Rp decorations are ignored.
Digits and separators must match exactly.
So fetcher.py should store a preformatted `display` string for every number
the brief may show (e.g. "7.123,45" or "+1,23%"), and the brief must copy it.
If the LLM reformats a number, the check fails. That's intended.

Small integers (<= SMALL_INT_ALLOW) are allowed by default: list numbering,
"5-day", "20-day", "14 hari", day-of-month in dates.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SMALL_INT_ALLOW = 31

# optional sign, a digit, optionally followed by digits/., ending in a digit
_NUM = re.compile(r"[+\-\u2212]?\d(?:[\d.,]*\d)?")


def numeric_tokens(text: str) -> set[str]:
    return set(_NUM.findall(text))


def _is_small_int(tok: str, limit: int) -> bool:
    bare = tok.lstrip("+-\u2212")
    return bare.isdigit() and int(bare) <= limit


def unverified_numbers(brief: str, data_text: str, small_int_allow: int = SMALL_INT_ALLOW) -> list[str]:
    allowed = numeric_tokens(data_text)
    bad = [
        t for t in numeric_tokens(brief)
        if t not in allowed and not _is_small_int(t, small_int_allow)
    ]
    return sorted(bad)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__.strip().splitlines()[2])
        return 2
    brief_path, data_path = map(Path, args)
    try:
        brief = brief_path.read_text()
        data_text = data_path.read_text()
    except OSError as e:
        print(f"ERROR: {e}")
        return 2
    bad = unverified_numbers(brief, data_text)
    if bad:
        print("UNVERIFIED: " + ", ".join(bad))
        return 1
    print("OK: all numbers found in data.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
