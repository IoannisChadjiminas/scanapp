"""The browser process is killed from outside when it misses the deadline."""

import json
import sys
import textwrap
from pathlib import Path

from supervisor import Supervisor

WORKER = textwrap.dedent(
    """
    import json, sys, time
    hang = False
    for raw in sys.stdin:
        cmd = json.loads(raw)
        if cmd.get("op") == "ready":
            print(json.dumps({"ok": True}), flush=True)
            continue
        url = cmd.get("url") or ""
        if "hang" in url:
            print(json.dumps({"stage": "navigation"}), file=sys.stderr, flush=True)
            time.sleep(30)
        print(json.dumps({
            "outcome": "offers", "reused": True, "cleared": True,
            "bytes": 12, "elapsed_ms": 5, "rows": [1], "stage": "parse",
        }), flush=True)
    """
)


def _supervisor(**kwargs) -> Supervisor:
    command = [sys.executable, "-c", WORKER]
    sup = Supervisor(
        command=command,
        attempt_seconds=kwargs.get("attempt_seconds", 0.4),
        kill_grace=kwargs.get("kill_grace", 0.2),
        exit_process=kwargs.get("exit_process", lambda code: (_ for _ in ()).throw(SystemExit(code))),
    )
    sup.start()
    return sup


def test_a_hang_is_killed_and_the_next_request_succeeds():
    sup = _supervisor()
    try:
        hung = sup.scrape("https://example.test/hang", "sess")
        assert hung["outcome"] == "timeout"
        assert hung["killed"] is True
        assert hung["stage"] == "navigation"
        assert sup.status()["state"] == "idle"
        done = sup.scrape("https://example.test/ok", "sess")
        assert done["outcome"] == "offers"
        assert done.get("killed") is not True
    finally:
        sup.stop()


def test_a_second_request_is_busy_immediately():
    import threading

    sup = _supervisor(attempt_seconds=2, kill_grace=0.2)
    try:
        box = {}

        def run():
            box["result"] = sup.scrape("https://example.test/hang", "sess")

        thread = threading.Thread(target=run)
        thread.start()
        from supervisor import LaneBusy

        raised = False
        for _ in range(50):
            try:
                sup.scrape("https://example.test/ok", "other")
            except LaneBusy:
                raised = True
                break
            except Exception:
                break
        thread.join(5)
        assert raised
    finally:
        sup.stop()


def test_three_failed_starts_exit():
    seen = []

    def stop(code):
        seen.append(code)
        raise SystemExit(code)

    sup = Supervisor(command=["/bin/false"], attempt_seconds=0.2, kill_grace=0.2, exit_process=stop)
    try:
        sup.start()
    except SystemExit:
        pass
    assert seen == [1]
