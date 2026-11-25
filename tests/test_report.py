import pytest

from brief.report import ReportError, strip_fences, write_verified

DATA = '{"focus": {"display": {"change_pct": "+1,30%", "end_close": "5.825"}}}'


def scripted(*replies):
    """A fake chat function that returns the given replies in order."""
    calls = []

    def fn(messages, model, cfg, key):
        calls.append([m["content"] for m in messages])
        return replies[len(calls) - 1]

    fn.calls = calls
    return fn


def test_passes_first_time():
    fn = scripted("BBCA naik +1,30% ke 5.825")
    assert write_verified("sys", "user", DATA, "m", {}, "k", chat_fn=fn) == "BBCA naik +1,30% ke 5.825"
    assert len(fn.calls) == 1


def test_retries_with_checker_feedback():
    fn = scripted("BBCA naik +1,35% ke 5.825", "BBCA naik +1,30% ke 5.825")
    out = write_verified("sys", "user", DATA, "m", {}, "k", chat_fn=fn)
    assert out == "BBCA naik +1,30% ke 5.825"
    assert "+1,35" in fn.calls[1][-1]            # the retry names the wrong number


def test_gives_up_after_retries():
    fn = scripted("+9,99%", "+9,99%", "+9,99%")
    with pytest.raises(ReportError):
        write_verified("sys", "user", DATA, "m", {}, "k", chat_fn=fn)
    assert len(fn.calls) == 3


def test_strip_fences():
    assert strip_fences("```\nhalo\n```") == "halo"
    assert strip_fences("```text\nhalo\n```") == "halo"
    assert strip_fences("halo") == "halo"
