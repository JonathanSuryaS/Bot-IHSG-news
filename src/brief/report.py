"""Write a report with a fixed model by calling the LLM directly, then send it.

Usage:
  brief-report analysis <weekly|monthly> <stock> [--send] [--print]

Why this exists: Hermes uses one default model for everything typed in chat.
To keep cheap commands (/watch, /alert) on a free model while analysis runs
on a stronger one, the /analysis skill just starts this script. The script:
  1. builds the data (brief.analysis) - no LLM
  2. asks the model in config/llm.yaml to write the report from that data
  3. checks every number with brief.verify; on failure it tells the model
     which numbers are wrong and retries (max 2 retries)
  4. sends the result to Telegram with `hermes send` (--send) and/or prints it
Errors are sent as a short message too, so the user is never left waiting.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from brief import CONFIG_DIR, DATA_DIR, REPO_ROOT
from brief.verify import unverified_numbers

PROMPTS_DIR = REPO_ROOT / "prompts"
HERMES_ENV = Path.home() / ".hermes" / ".env"
HERMES_BIN = Path.home() / ".local" / "bin" / "hermes"
PERIOD_WORDS = {"weekly": "week", "mingguan": "week", "week": "week",
                "monthly": "month", "bulanan": "month", "month": "month"}
MAX_RETRIES = 2
MAX_CHARS = 3800  # Telegram's hard limit is 4096


class ReportError(RuntimeError):
    """A problem worth telling the user about (in Indonesian)."""


# ---------- config + key ----------

def load_llm_cfg() -> dict:
    import yaml

    return yaml.safe_load((CONFIG_DIR / "llm.yaml").read_text())


def _read_env_file(path: Path) -> dict[str, str]:
    out = {}
    try:
        for line in path.read_text().splitlines():
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$", line)
            if m:
                out[m.group(1)] = m.group(2).strip().strip("'\"")
    except OSError:
        pass
    return out


def api_key() -> str:
    """NIBIE_API_KEY from env, then repo .env, then the key Hermes saved."""
    if os.environ.get("NIBIE_API_KEY"):
        return os.environ["NIBIE_API_KEY"]
    repo_env = _read_env_file(REPO_ROOT / ".env")
    if repo_env.get("NIBIE_API_KEY"):
        return repo_env["NIBIE_API_KEY"]
    for name, value in _read_env_file(HERMES_ENV).items():
        if name.startswith("HERMES_CUSTOM_ROUTER_NIBIE_APP_") and name.endswith("_API_KEY") and value:
            return value
    raise ReportError("API key NibieRouter tidak ditemukan")


# ---------- LLM call ----------

def chat(messages: list[dict], model: str, cfg: dict, key: str) -> str:
    body = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": cfg.get("max_output_tokens", 4000),
    }).encode()
    req = urllib.request.Request(
        cfg["base_url"].rstrip("/") + "/chat/completions", data=body, method="POST",
        # NibieRouter sits behind Cloudflare, which blocks the default
        # "Python-urllib" User-Agent (error 1010).
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": "ihsg-brief/0.1 (+python)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=cfg.get("timeout_seconds", 180)) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        raise ReportError(f"model {model} menolak permintaan (HTTP {e.code}): {detail}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ReportError(f"model {model} tidak bisa dihubungi: {e}") from e
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise ReportError(f"jawaban model {model} tidak terbaca") from e
    return strip_fences(text)


def strip_fences(text: str) -> str:
    text = text.strip()
    m = re.fullmatch(r"```[a-zA-Z]*\n(.*)\n```", text, flags=re.S)
    return (m.group(1) if m else text).strip()


def write_verified(system: str, user: str, data_text: str, model: str, cfg: dict, key: str,
                   chat_fn=chat) -> str:
    """Ask for the report; re-ask with the checker's findings until it passes."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for attempt in range(MAX_RETRIES + 1):
        draft = chat_fn(messages, model, cfg, key)
        bad = unverified_numbers(draft, data_text)
        too_long = len(draft) > MAX_CHARS
        if not bad and not too_long and draft:
            return draft
        if attempt == MAX_RETRIES:
            break
        problems = []
        if bad:
            problems.append(
                "These numbers are not in the JSON: " + ", ".join(bad)
                + ". Copy numbers only from `display` fields, character for character, or leave them out."
            )
        if too_long:
            problems.append(f"The report has {len(draft)} characters; it must be under 3.500.")
        if not draft:
            problems.append("The report was empty.")
        messages += [{"role": "assistant", "content": draft},
                     {"role": "user", "content": " ".join(problems) + " Rewrite the full report."}]
    raise ReportError("laporan gagal lolos pengecekan angka")


# ---------- reports ----------

def analysis_report(period_word: str, stock: str) -> str:
    from brief.analysis import StockNotFound, build

    period = PERIOD_WORDS.get(period_word.lower())
    if not period:
        raise ReportError("Format: /analysis <weekly|monthly> <kode saham>")
    try:
        data = build(period, stock)
    except StockNotFound:
        raise ReportError(f'Saham "{stock}" tidak ditemukan. Pakai kode 4 huruf IDX, '
                          "contoh: /analysis weekly BMRI")
    except Exception as e:
        raise ReportError(f"data analisis tidak tersedia ({type(e).__name__})") from e

    data_text = json.dumps(data, ensure_ascii=False, indent=1)
    (DATA_DIR / f"analysis-{period}.json").write_text(data_text)

    cfg = load_llm_cfg()
    label = "mingguan" if period == "week" else "bulanan"
    user = (f"Request: analisis {label} untuk {stock}.\n\nJSON:\n{data_text}")
    system = (PROMPTS_DIR / "analysis.md").read_text()
    return write_verified(system, user, data_text, cfg["models"]["analysis"], cfg, api_key())


# ---------- output ----------

def send_telegram(text: str) -> None:
    hermes = str(HERMES_BIN) if HERMES_BIN.exists() else "hermes"
    r = subprocess.run([hermes, "send", "-t", "telegram", "-q"], input=text, text=True,
                       capture_output=True, timeout=60)
    if r.returncode != 0:
        print(f"hermes send failed ({r.returncode}): {r.stderr.strip()[:300]}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    send = "--send" in args
    show = "--print" in args or not send
    rest = [a for a in args if a not in ("--send", "--print")]
    if len(rest) < 3 or rest[0] != "analysis":
        print("Usage: brief-report analysis <weekly|monthly> <stock> [--send] [--print]", file=sys.stderr)
        return 2
    period_word, stock = rest[1], " ".join(rest[2:])

    ok = True
    try:
        text = analysis_report(period_word, stock)
    except ReportError as e:
        ok = False
        text = str(e) if str(e).startswith(("Format:", "Saham ")) else f"⚠️ Analisis gagal: {e}"

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "analysis-report.txt").write_text(text)
    if send:
        send_telegram(text)
    if show:
        print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
