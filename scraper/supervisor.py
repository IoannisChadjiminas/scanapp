"""Runs the browser in its own process group and kills that group when it misses a deadline.

The FastAPI process never calls Selenium. A hung Chrome cannot hold a thread here,
so the lane state always moves on.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

ATTEMPT_SECONDS = float(os.environ.get("SCRAPER_ATTEMPT_SECONDS", "90"))
KILL_GRACE_S = float(os.environ.get("SCRAPER_KILL_GRACE_S", "10"))
MAX_RSS_MB = float(os.environ.get("SCRAPER_WORKER_MAX_RSS_MB", "1100"))
MAX_PAGES = int(os.environ.get("SCRAPER_WORKER_MAX_PAGES", "200"))
WINDOW_S = float(os.environ.get("SCRAPER_BROWSER_LIFETIME_S", "1800"))
ROTATE_BEFORE_S = float(os.environ.get("DAILY_SESSION_ROTATE_BEFORE_S", "120"))
LANE = os.environ.get("SCRAPER_LANE", "a").strip() or "a"


class LaneBusy(Exception):
    """A scrape is already running in this process."""


class LaneUnavailable(Exception):
    def __init__(self, state: str) -> None:
        self.state = state
        super().__init__(state)


class Supervisor:
    def __init__(
        self,
        *,
        command: list[str] | None = None,
        attempt_seconds: float = ATTEMPT_SECONDS,
        kill_grace: float = KILL_GRACE_S,
        exit_process=None,
    ) -> None:
        self.command = command or [sys.executable, "-m", "worker"]
        self.attempt_seconds = attempt_seconds
        self.kill_grace = kill_grace
        self.exit_process = exit_process if exit_process is not None else os._exit
        self.state = "starting"
        self.session_id = ""
        self.cleared = False
        self.pages = 0
        self.window_started = 0.0
        self.busy_since = 0.0
        self.restarts = 0
        self.start_failures = 0
        self.last_restart_reason = ""
        self.cooldown_until = 0.0
        self.last_outcome = ""
        self.last_ok_at = 0.0
        self.stage = ""
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._stderr: threading.Thread | None = None
        self._stopped = False

    def start(self) -> None:
        while self.state != "idle" and self.start_failures < 3 and not self._stopped:
            self._spawn("start")
        if self.state != "idle" and not self._stopped:
            self.exit_process(1)

    def stop(self) -> None:
        self._stopped = True
        self._kill("stop")

    def status(self) -> dict:
        with self._lock:
            now = time.time()
            busy_for = now - self.busy_since if self.state == "busy" and self.busy_since else 0.0
            window_age = now - self.window_started if self.window_started else 0.0
            return {
                "lane": LANE,
                "state": self.state,
                "session_id": self.session_id,
                "cleared": self.cleared,
                "pages": self.pages,
                "window_age_s": round(window_age, 1),
                "busy_for_s": round(busy_for, 1),
                "restarts": self.restarts,
                "last_restart_reason": self.last_restart_reason,
                "cooldown_until": self.cooldown_until,
                "last_outcome": self.last_outcome,
                "last_ok_at": self.last_ok_at,
                "attempt_seconds": self.attempt_seconds,
                "stage": self.stage,
            }

    def warm(self, session_id: str) -> dict:
        return self._call({"op": "warm", "session_id": session_id}, timeout=self.kill_grace + 30)

    def scrape(self, url: str, session_id: str) -> dict:
        self._recycle_if_due(session_id)
        with self._lock:
            if self.state == "cooling" and self.cooldown_until <= time.time():
                self.state = "idle"
            if self.state == "busy":
                raise LaneBusy()
            if self.state != "idle":
                raise LaneUnavailable(self.state)
            if self.cooldown_until > time.time():
                raise LaneUnavailable("cooling")
            self.state = "busy"
            self.busy_since = time.time()
            self.stage = ""
        try:
            result = self._call(
                {
                    "op": "scrape",
                    "url": url,
                    "session_id": session_id,
                    "deadline_s": self.attempt_seconds,
                },
                timeout=self.attempt_seconds + self.kill_grace,
            )
        except Exception:
            self._finish_busy()
            raise
        self._note_result(result, session_id)
        self._finish_busy()
        return result

    def note_rate_limit(self, seconds: float) -> None:
        with self._lock:
            self.cooldown_until = time.time() + seconds
            self.state = "cooling"

    def _finish_busy(self) -> None:
        with self._lock:
            self.busy_since = 0.0
            if self.state == "busy":
                self.state = "cooling" if self.cooldown_until > time.time() else "idle"

    def _note_result(self, result: dict, session_id: str) -> None:
        with self._lock:
            self.last_outcome = str(result.get("outcome") or "")
            self.stage = str(result.get("stage") or self.stage)
            if result.get("reused") is True or result.get("cleared") is True:
                self.cleared = bool(result.get("cleared") or self.cleared)
            if self.last_outcome == "offers":
                self.cleared = True
                self.last_ok_at = time.time()
            if result.get("outcome") in {"offers", "empty", "timeout", "challenge_unsolved", "rate_limited", "wrong_product"}:
                self.pages += 1
            if not self.session_id:
                self.session_id = session_id
                self.window_started = time.time()

    def _recycle_if_due(self, session_id: str) -> None:
        with self._lock:
            if self.state != "idle" or self._proc is None:
                return
            age = time.time() - self.window_started if self.window_started else 0.0
            expired = self.window_started and age >= max(0.0, WINDOW_S - ROTATE_BEFORE_S)
            too_many = self.pages >= MAX_PAGES
            too_big = _rss_mb(self._proc.pid) >= MAX_RSS_MB
            if not (expired or too_many or too_big):
                return
            reason = "memory" if too_big else "pages" if too_many else "window"
        self._restart(reason)
        if session_id:
            with self._lock:
                self.session_id = session_id

    def _call(self, payload: dict, timeout: float, respawn: bool = True) -> dict:
        proc = self._proc
        if proc is None or proc.poll() is not None or proc.stdin is None or proc.stdout is None:
            if not respawn:
                return {"outcome": "timeout", "killed": True, "stage": self.stage, "bytes": None}
            self._spawn("respawn")
            proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            return {"outcome": "timeout", "killed": True, "stage": self.stage, "bytes": None}
        box: dict = {}

        def read() -> None:
            box["line"] = proc.stdout.readline() if proc.stdout is not None else b""

        try:
            proc.stdin.write((json.dumps(payload) + "\n").encode())
            proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            return {"outcome": "timeout", "killed": True, "stage": self.stage, "bytes": None}
        reader = threading.Thread(target=read, name="scraper-worker-read", daemon=True)
        reader.start()
        reader.join(timeout)
        if reader.is_alive() or not box.get("line"):
            stage = self.stage
            self._kill("deadline")
            if respawn:
                self._spawn("deadline")
            return {"outcome": "timeout", "killed": True, "stage": stage, "bytes": None}
        try:
            body = json.loads(box["line"].decode())
        except ValueError:
            return {"outcome": "error", "error": "bad-reply", "stage": self.stage}
        if not isinstance(body, dict):
            return {"outcome": "error", "error": "bad-reply", "stage": self.stage}
        return body

    def _spawn(self, reason: str) -> None:
        if self._stopped:
            return
        with self._lock:
            self.state = "starting" if self._proc is None else "restarting"
            self.last_restart_reason = reason
        try:
            proc = subprocess.Popen(
                self.command,
                cwd=str(HERE),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError:
            self._failed_start(reason)
            return
        with self._lock:
            self._proc = proc
            self.restarts += 1 if reason != "start" else 0
        self._stderr = threading.Thread(target=self._read_stderr, args=(proc,), name="scraper-worker-log", daemon=True)
        self._stderr.start()
        ready = self._call({"op": "ready"}, timeout=self.kill_grace + 5, respawn=False)
        with self._lock:
            if ready.get("ok") is True and self.state in {"starting", "restarting"}:
                self.state = "idle"
                self.start_failures = 0
            else:
                self.start_failures += 1
        if self.start_failures >= 3:
            self.exit_process(1)

    def _failed_start(self, reason: str) -> None:
        with self._lock:
            self.start_failures += 1
            self.last_restart_reason = reason
            self.state = "restarting"
        if self.start_failures >= 3:
            self.exit_process(1)

    def _restart(self, reason: str) -> None:
        self._kill(reason)
        self._spawn(reason)

    def _restart_later(self, reason: str) -> None:
        threading.Thread(target=self._restart, args=(reason,), name="scraper-restart", daemon=True).start()

    def _kill(self, reason: str) -> None:
        proc = self._proc
        with self._lock:
            if self.state != "starting":
                self.state = "restarting"
            self.last_restart_reason = reason
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            return
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                return
            proc.wait(timeout=5)

    def _read_stderr(self, proc: subprocess.Popen) -> None:
        if proc.stderr is None:
            return
        for raw in proc.stderr:
            line = raw.decode(errors="replace").strip()
            if not line:
                continue
            try:
                body = json.loads(line)
            except ValueError:
                continue
            if isinstance(body, dict) and body.get("stage"):
                self.stage = str(body["stage"])


def _rss_mb(pid: int) -> float:
    try:
        import psutil

        proc = psutil.Process(pid)
        total = proc.memory_info().rss
        for child in proc.children(recursive=True):
            try:
                total += child.memory_info().rss
            except psutil.Error:
                continue
        return total / (1024 * 1024)
    except Exception:
        return 0.0
