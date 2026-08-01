"""ponytail check: _get retries transient errors, then gives up after 3 tries."""
import sys
from pathlib import Path
from unittest import mock
import urllib.error

sys.path.insert(0, str(Path(__file__).parent))
import trading_data as td


class _Resp:
    def read(self): return b'{"ok": true}'
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_retries_then_succeeds():
    calls = {"n": 0}
    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError("timed out")
        return _Resp()
    with mock.patch.object(td.urllib.request, "urlopen", flaky), mock.patch.object(td.time, "sleep", lambda *_: None):
        assert td._get("http://x", {}) == {"ok": True}
        assert calls["n"] == 3  # failed twice, succeeded on 3rd


def test_gives_up_after_3():
    def always_fail(*a, **k):
        raise urllib.error.URLError("reset")
    with mock.patch.object(td.urllib.request, "urlopen", always_fail), mock.patch.object(td.time, "sleep", lambda *_: None):
        try:
            td._get("http://x", {})
            assert False, "should have raised"
        except urllib.error.URLError:
            pass


if __name__ == "__main__":
    test_retries_then_succeeds()
    test_gives_up_after_3()
    print("ok")
