"""ponytail check: _poly retries transient errors, then gives up after 3 tries."""
import sys, types
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import requests
import trading_data as td


class _Resp:
    def raise_for_status(self): pass
    def json(self): return {"ok": True}


def test_retries_then_succeeds():
    calls = {"n": 0}
    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.Timeout("read timed out")
        return _Resp()
    with mock.patch.object(requests, "get", flaky), mock.patch.object(td.time, "sleep", lambda *_: None):
        assert td._poly("/x") == {"ok": True}
        assert calls["n"] == 3  # failed twice, succeeded on 3rd


def test_gives_up_after_3():
    def always_fail(*a, **k):
        raise requests.ConnectionError("reset")
    with mock.patch.object(requests, "get", always_fail), mock.patch.object(td.time, "sleep", lambda *_: None):
        try:
            td._poly("/x")
            assert False, "should have raised"
        except requests.ConnectionError:
            pass


if __name__ == "__main__":
    test_retries_then_succeeds()
    test_gives_up_after_3()
    print("ok")
