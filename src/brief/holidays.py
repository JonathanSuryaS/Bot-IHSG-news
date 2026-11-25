"""Is today an IDX trading day?

Exit codes for `brief-check-day` (so cron/Hermes can branch on it):
  0  trading day        -> go ahead and fetch
  1  weekend / holiday  -> send nothing (or a short "market closed" note)
  2  config problem     -> treat as failure, send "No fresh data today"
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from brief import CONFIG_DIR

WIB = ZoneInfo("Asia/Jakarta")


class HolidayConfigError(RuntimeError):
    pass


def today_wib() -> date:
    return datetime.now(WIB).date()


def load_holidays(year: int, config_dir: Path = CONFIG_DIR) -> dict[date, str]:
    import yaml  # local import so the pure functions stay dependency-free

    path = config_dir / f"idx_holidays_{year}.yaml"
    if not path.exists():
        raise HolidayConfigError(f"missing {path.name}; copy the IDX calendar for {year}")
    raw = yaml.safe_load(path.read_text()) or {}
    entries = raw.get("holidays") or []
    if not entries:
        raise HolidayConfigError(f"{path.name} has no holidays listed; fill it from IDX")
    out: dict[date, str] = {}
    for e in entries:
        d = e["date"] if isinstance(e["date"], date) else date.fromisoformat(str(e["date"]))
        out[d] = e.get("name", "")
    return out


def is_trading_day(d: date, holidays: dict[date, str]) -> tuple[bool, str]:
    if d.weekday() >= 5:
        return False, "weekend"
    if d in holidays:
        return False, f"IDX holiday: {holidays[d]}"
    return True, "trading day"


def main() -> int:
    d = today_wib()
    try:
        holidays = load_holidays(d.year)
    except HolidayConfigError as e:
        print(f"CONFIG_ERROR: {e}")
        return 2
    ok, reason = is_trading_day(d, holidays)
    print(f"{d.isoformat()}: {reason}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
