import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from threading import Barrier, Event
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw
import pytest

from app.admission import ScanLimiter
from app.config import Settings
from app.recognition.local_match import LocalArtworkVerifier
from app.recognition.runtime import LaneRuntime, Runtime, scan_lane
import app.recognition.runtime as runtime_module


def _fake_readers(monkeypatch):
    readers = []

    def make_reader(**kwargs):
        reader = SimpleNamespace(engine=object(), shared_from=None)
        reader.share_inference_sessions_from = lambda parent: setattr(reader, 'shared_from', parent)
        readers.append(reader)
        return reader

    monkeypatch.setattr(runtime_module, 'CardOcr', make_reader)
    monkeypatch.setattr(runtime_module, 'DinoEmbedder', lambda *args: object())
    return readers


def _runtime(tmp_path, lanes, **flags):
    return Runtime(Settings(_env_file=None, data_dir=tmp_path, scan_lanes=lanes, **flags))


def test_one_lane_is_the_runtime_itself(monkeypatch, tmp_path):
    readers = _fake_readers(monkeypatch)
    runtime = _runtime(tmp_path, 1, parallel_grading=True, ocr_parallel_regions=True)
    runtime.load(SimpleNamespace())
    assert len(readers) == 3
    with runtime.lane() as lane:
        assert lane is runtime
        assert lane.require()[2] is runtime.ocr


def test_extra_lane_owns_readers_and_workers_and_shares_sessions(monkeypatch, tmp_path):
    readers = _fake_readers(monkeypatch)
    runtime = _runtime(tmp_path, 2, parallel_grading=True, ocr_parallel_regions=True)
    snapshot = SimpleNamespace(model_name='m', model_revision='r', catalogue_version='c')
    runtime.load(snapshot)
    assert runtime.ready and len(readers) == 6
    with runtime.lane() as first, runtime.lane() as second:
        assert first is runtime and isinstance(second, LaneRuntime)
        # Every reader of the second lane shares lane 0's sessions, never its engine.
        for reader in (second.ocr, second.grading_ocr, second.ocr.region_reader):
            assert reader.shared_from is runtime.ocr and reader.engine is not runtime.ocr.engine
        assert second.ocr is not runtime.ocr
        assert second.grading_ocr is not runtime.grading_ocr
        assert second.ocr.auxiliary_gate is not runtime.ocr.auxiliary_gate
        assert second.grading_ocr.auxiliary_gate is second.ocr.auxiliary_gate
        assert second.region_executor is not runtime.region_executor
        assert second.grading_executor is not runtime.grading_executor
        assert second.grading_slots is not runtime.grading_slots
        assert second.require() == (snapshot, runtime.embedder, second.ocr)
        assert second.snapshot is snapshot and second.printing_index is runtime.printing_index
        assert second.versions() == runtime.versions()
    extra = runtime._extra_lanes[0]
    workers = (extra.region_executor, extra.grading_executor)
    runtime.load(snapshot)
    assert all(worker._shutdown for worker in workers)
    runtime.close()
    assert runtime._extra_lanes == [] and runtime._free_lanes is None


def test_lane_checkout_hands_out_distinct_lanes_and_waits_when_all_are_busy(monkeypatch, tmp_path):
    _fake_readers(monkeypatch)
    runtime = _runtime(tmp_path, 2)
    runtime.load(SimpleNamespace())
    held, release, third = Barrier(3), Event(), Event()
    seen = []

    def hold():
        with runtime.lane() as lane:
            seen.append(lane)
            held.wait()
            release.wait(5)

    def late():
        with runtime.lane() as lane:
            seen.append(lane)
            third.set()

    with ThreadPoolExecutor(3) as pool:
        holders = [pool.submit(hold) for _ in range(2)]
        held.wait(5)
        waiting = pool.submit(late)
        assert not third.wait(.2)
        release.set()
        for future in (*holders, waiting):
            future.result(5)
    assert seen[0] is not seen[1] and seen[2] in seen[:2]


def test_runtime_without_lanes_is_used_directly():
    double = SimpleNamespace(ocr=object())
    with scan_lane(double) as lane:
        assert lane is double


def test_limiter_admits_one_scan_per_lane():
    async def run():
        limiter = ScanLimiter(wait_limit=1, slots=2)
        assert await limiter.acquire() and await limiter.acquire()
        waiter = asyncio.create_task(limiter.acquire())
        await asyncio.sleep(0)
        assert not waiter.done()
        assert await limiter.acquire() is False
        await limiter.release()
        assert await waiter is True
        await limiter.release()
        await limiter.release()
        assert limiter._active == 0

    asyncio.run(run())


def test_artwork_reference_cache_survives_concurrent_eviction(tmp_path):
    verifier = LocalArtworkVerifier(tmp_path, max_references=2)
    verifier.feature_store = SimpleNamespace(
        features=lambda card_id, *args: SimpleNamespace(card_id=card_id))
    keys = [f'card-{n}' for n in range(6)]

    def hammer(offset):
        for n in range(400):
            card_id = keys[(n + offset) % len(keys)]
            assert verifier._reference_features(card_id, 'x', (0, 0, 1, 1), 1000, .04).card_id == card_id

    with ThreadPoolExecutor(4) as pool:
        for future in [pool.submit(hammer, offset) for offset in range(4)]:
            future.result()
    assert len(verifier._cache) <= 2


MODELS = Path(os.environ.get('SCANAPP_TEST_MODELS_DIR', '/nonexistent'))


@pytest.mark.skipif(not (MODELS / 'PP-OCRv6_det_small.onnx').is_file(),
                    reason='set SCANAPP_TEST_MODELS_DIR to a directory with the ONNX models')
def test_two_real_lanes_read_concurrently_like_one(tmp_path):
    (tmp_path / 'models').symlink_to(MODELS, target_is_directory=True)
    runtime = Runtime(Settings(_env_file=None, data_dir=tmp_path, scan_lanes=2, ort_intra_threads=2,
                               dino_intra_threads=2, parallel_grading=True, ocr_parallel_regions=True))
    runtime.load(SimpleNamespace())
    assert runtime.error is None
    cards = []
    for n in range(4):
        image = Image.new('RGB', (630, 880), (240, 236, 220))
        draw = ImageDraw.Draw(image)
        draw.text((40, 30), f'Pikachu {n}', fill=(0, 0, 0), font_size=48)
        draw.text((40, 820), f'{n + 10}/102', fill=(0, 0, 0), font_size=32)
        cards.append(image)

    def scan(lane, image):
        ocr = lane.ocr.read(image)
        return ocr.name_text, ocr.collector_text, lane.embedder.embed(image, 'pad').tobytes()

    with runtime.lane() as lane:
        expected = [scan(lane, image) for image in cards]

    def worker(n):
        with runtime.lane() as lane:
            return [scan(lane, cards[(n + i) % len(cards)]) for i in range(len(cards))]

    with ThreadPoolExecutor(2) as pool:
        for n, future in enumerate([pool.submit(worker, n) for n in range(6)]):
            got = future.result(120)
            assert got == [expected[(n + i) % len(cards)] for i in range(len(cards))]
    runtime.close()


def test_lanes_share_serialized_sqlite_connections(tmp_path):
    from app.db import Databases, SerializedConnection

    one = Databases(Settings(_env_file=None, data_dir=tmp_path / 'one', scan_lanes=1))
    two = Databases(Settings(_env_file=None, data_dir=tmp_path / 'two', scan_lanes=2))
    try:
        assert not isinstance(one.catalog, SerializedConnection)
        assert isinstance(two.catalog, SerializedConnection) and isinstance(two.results, SerializedConnection)
        two.catalog.executemany('INSERT INTO cards (id, provider_id, name, set_id, set_name, collector_number) '
                                'VALUES (?, ?, ?, ?, ?, ?)',
                                [(f'c{n}', 'p', f'Card {n}', 's', 'Set', str(n)) for n in range(200)])
        two.catalog.commit()

        def hammer(offset):
            for n in range(300):
                card_id = f'c{(n + offset) % 200}'
                row = two.catalog.execute('SELECT * FROM cards WHERE id = ?', (card_id,)).fetchone()
                assert row['id'] == card_id
                assert len(two.catalog.execute('SELECT id FROM cards LIMIT 50').fetchall()) == 50

        with ThreadPoolExecutor(4) as pool:
            for future in [pool.submit(hammer, offset) for offset in range(4)]:
                future.result()
    finally:
        one.close()
        two.close()
