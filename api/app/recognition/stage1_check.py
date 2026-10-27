"""One background thread that re-runs the full pipeline after a stage 1 answer.

It never takes a live scan slot. If a scan is already running or waiting, the
check is skipped. Disagreements are logged and, when captures are on, the
upload is kept next to the other capture files.
"""
from __future__ import annotations

import logging
import queue
import random
import threading
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger('scan.diagnostics')


@dataclass
class CheckJob:
    scan_id: str
    card_id: str
    data: bytes
    recognize: object
    store_dir: Path | None = None
    # 'phone': the re-run had the phone's text and outline; 'photo': the upload alone.
    inputs: str = 'photo'


class Stage1Checker:
    def __init__(self) -> None:
        self._queue: queue.Queue[CheckJob | None] = queue.Queue(maxsize=4)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.answers = 0
        self.checks = 0
        self.disagreements = 0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name='stage1-check', daemon=True)
        self._thread.start()

    def note_answer(self) -> None:
        with self._lock:
            self.answers += 1

    def submit(self, job: CheckJob, *, sample_rate: float, busy: bool) -> None:
        if busy or random.random() > max(0.0, min(1.0, sample_rate)):
            log.info('stage1_check scan_id=%s skipped busy=%s', job.scan_id, str(busy).lower())
            return
        try:
            self._queue.put_nowait(job)
        except queue.Full:
            log.info('stage1_check scan_id=%s skipped busy=true', job.scan_id)

    def stop(self) -> None:
        if self._thread is None:
            return
        self._queue.put(None)
        self._thread.join(timeout=2)
        self._thread = None

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                return
            try:
                self.run_job(job)
            except Exception:
                log.exception('stage1_check failed scan_id=%s', job.scan_id)

    def run_job(self, job: CheckJob) -> bool:
        result = job.recognize(job.data)
        suggestions = list(getattr(result, 'suggestions', None) or [])
        full = suggestions[0].card_id if suggestions else None
        agree = bool(full) and (full == job.card_id or full.split(':', 1)[-1] == job.card_id.split(':', 1)[-1])
        log.info('stage1_check scan_id=%s stage1_card=%s full_card=%s agree=%s inputs=%s',
                 job.scan_id, job.card_id, full or 'none', str(agree).lower(), job.inputs)
        with self._lock:
            self.checks += 1
            if not agree:
                self.disagreements += 1
        if not agree and job.store_dir is not None:
            job.store_dir.mkdir(parents=True, exist_ok=True)
            (job.store_dir / f'{job.scan_id}-stage1-disagree.jpg').write_bytes(job.data)
        return agree
