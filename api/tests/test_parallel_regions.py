from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from PIL import Image
import pytest

from app.config import Settings
from app.recognition.auxiliary_work import AuxiliaryWorkGate
from app.recognition.grading_control import GradingCancelled, grading_cancellation_scope
from app.recognition.ocr import CardOcr
from app.recognition.runtime import Runtime
import app.recognition.runtime as runtime_module


def test_title_and_footer_overlap_with_independent_engines_and_equal_observations():
    title_entered,footer_entered=Event(),Event()
    reader=CardOcr.__new__(CardOcr);reader.engine=object()
    def title(image):
        title_entered.set()
        assert footer_entered.wait(2),'Footer must overlap title'
        return ['Pikachu'],[.99]
    def footer(image):
        footer_entered.set()
        assert title_entered.wait(2),'Title must overlap footer'
        return ['35/108'],[.98]
    reader._run=title
    reader.region_reader=SimpleNamespace(engine=object(),_run=footer)
    reader.auxiliary_gate=AuxiliaryWorkGate()
    with ThreadPoolExecutor(max_workers=1) as executor:
        reader.region_executor=executor
        result=reader.read(Image.new('RGB',(600,840)))
    assert not result.failed and result.name_text=='Pikachu' and result.collector_text=='35/108'
    assert [(h.text,h.confidence,h.region) for h in result.hits]==[
        ('Pikachu',.99,'name'),('35/108',.98,'collector')]
    assert [p['region'] for p in result.passes]==['name','collector']
    assert result.passes[1]['parallel'] is True


@pytest.mark.parametrize('failed_region',['name','collector'])
def test_failures_drain_worker_and_release_lane_without_late_evidence(failed_region):
    finished=Event();reader=CardOcr.__new__(CardOcr);reader.engine=object()
    def title(image):
        if failed_region=='name':raise ValueError('failed title')
        return ['Pikachu'],[.99]
    def footer(image):
        try:
            if failed_region=='collector':raise ValueError('failed collector')
            return ['35/108'],[.98]
        finally:finished.set()
    reader._run=title;reader.region_reader=SimpleNamespace(engine=object(),_run=footer)
    reader.auxiliary_gate=AuxiliaryWorkGate()
    with ThreadPoolExecutor(max_workers=1) as executor:
        reader.region_executor=executor
        result=reader.read(Image.new('RGB',(600,840)))
    assert result.failed and finished.is_set() and len(result.passes)==2
    assert not reader.auxiliary_gate.active


def test_one_auxiliary_lane_prioritizes_card_after_inflight_grading():
    gate=AuxiliaryWorkGate();running,release,card_entered=Event(),Event(),Event()
    order=[]
    def first_grade():
        with gate.grading():
            running.set();assert release.wait(2)
    def card():
        with gate.card():
            order.append('card');card_entered.set()
    def second_grade():
        with gate.grading():
            assert card_entered.is_set();order.append('grading')
    with ThreadPoolExecutor(max_workers=3) as workers:
        first=workers.submit(first_grade);assert running.wait(2)
        foreground=workers.submit(card)
        # Synchronize on the condition, not scheduler-dependent sleep timing.
        with gate.condition:
            assert gate.condition.wait_for(lambda:gate.card_waiters==1,timeout=2)
        second=workers.submit(second_grade);release.set()
        first.result();foreground.result();second.result()
    assert order==['card','grading'] and not gate.active


def test_cancelled_grade_can_leave_a_busy_lane_without_interrupting_card():
    gate=AuxiliaryWorkGate();stop=Event()
    with gate.card(), grading_cancellation_scope(stop):
        stop.set()
        with pytest.raises(GradingCancelled),gate.grading():
            pytest.fail('Cancelled job must not infer')
        assert gate.active
    assert not gate.active


def test_busy_auxiliary_lane_uses_serial_ocr_without_waiting_or_extra_engine():
    gate=AuxiliaryWorkGate();reader=CardOcr.__new__(CardOcr);reader.engine=object()
    observations=iter([(['Pikachu'],[.99]),(['35/108'],[.98])])
    reader._run=lambda image:next(observations)
    reader.region_reader=SimpleNamespace(engine=object(),_run=lambda image:pytest.fail('Lane is busy'))
    reader.auxiliary_gate=gate
    with ThreadPoolExecutor(max_workers=1) as executor,gate.grading():
        reader.region_executor=executor
        result=reader.read(Image.new('RGB',(600,840)))
        assert gate.active
    assert not result.failed and result.collector_text=='35/108'
    assert all('parallel' not in p for p in result.passes) and not gate.active


def test_lane_reservation_is_nonblocking_exclusive_and_recoverable():
    gate=AuxiliaryWorkGate()
    assert gate.try_reserve_card()
    assert not gate.try_reserve_card()
    gate.release_card()
    assert gate.try_reserve_card()
    gate.release_card()


def test_card_priority_blocks_new_grading_but_not_auxiliary_card_work():
    gate = AuxiliaryWorkGate(); entered = Event(); waiting = Event()
    def grade():
        waiting.set()
        with gate.grading():
            entered.set()
    with ThreadPoolExecutor(max_workers=1) as executor:
        with gate.prioritize_card():
            task = executor.submit(grade)
            assert waiting.wait(2) and not entered.is_set()
            assert gate.try_reserve_card()
            gate.release_card()
            with gate.prioritize_card():
                assert gate.card_priority == 2
            assert gate.card_priority == 1
        task.result(timeout=2)
    assert entered.is_set() and not gate.active and gate.card_priority == 0


def test_card_priority_cancellation_and_failures_release_reservation():
    gate = AuxiliaryWorkGate(); stop = Event()
    with pytest.raises(ValueError):
        with gate.prioritize_card(), grading_cancellation_scope(stop):
            stop.set()
            with pytest.raises(GradingCancelled), gate.grading():
                pytest.fail('Cancelled grading may not infer')
            raise ValueError('foreground failed')
    assert gate.card_priority == 0 and not gate.active


def test_runtime_isolates_region_state_and_releases_executor_on_reload(monkeypatch,tmp_path):
    readers=[]
    def make_reader(**kwargs):
        obj=SimpleNamespace(engine=object(),shared_from=None)
        obj.share_inference_sessions_from=lambda parent:setattr(obj,'shared_from',parent)
        readers.append(obj);return obj
    monkeypatch.setattr(runtime_module,'CardOcr',make_reader)
    monkeypatch.setattr(runtime_module,'DinoEmbedder',lambda *args:object())
    runtime=Runtime(Settings(_env_file=None,data_dir=tmp_path,parallel_grading=True,
                             ocr_parallel_regions=True))
    runtime.load(SimpleNamespace());assert runtime.ready and len(readers)==3
    assert runtime.ocr.region_reader is readers[2]
    assert runtime.ocr.region_reader.shared_from is runtime.ocr
    assert runtime.grading_ocr.auxiliary_gate is runtime.ocr.auxiliary_gate
    previous=runtime.region_executor
    assert previous._max_workers==1
    runtime.load(SimpleNamespace());assert previous._shutdown
    runtime.close();assert runtime.region_executor is None


@pytest.mark.parametrize('failed_half', [None, 'left', 'right'])
def test_footer_halves_overlap_keep_conflicts_order_and_drain_failures(failed_half):
    left_entered, right_entered = Event(), Event()
    reader = CardOcr.__new__(CardOcr); reader.engine = object()
    reader.parallel_footer_halves = True
    def main(image):
        if image.width == 600:
            return ['Pikachu'], [.99]
        left_entered.set()
        assert right_entered.wait(2)
        if failed_half == 'left':
            raise ValueError('left failed')
        return ['35/108'], [.98]
    def auxiliary(image):
        if image.width == 600:
            return ['retreat'], [.99]
        right_entered.set()
        assert left_entered.wait(2)
        if failed_half == 'right':
            raise ValueError('right failed')
        return ['35/109'], [.97]
    reader._run = main
    reader.region_reader = SimpleNamespace(engine=object(), _run=auxiliary)
    reader.auxiliary_gate = AuxiliaryWorkGate()
    with ThreadPoolExecutor(max_workers=1) as executor:
        reader.region_executor = executor
        observed = reader.read(Image.new('RGB', (600, 840)))
    assert not observed.failed and not reader.auxiliary_gate.active
    numbers = [h.text for h in observed.hits if '/' in h.text]
    expected = ([] if failed_half == 'left' else ['35/108']) + ([] if failed_half == 'right' else ['35/109'])
    assert numbers == expected
    assert len(observed.passes) == 4
    assert observed.passes[-1]['parallel'] is True
    assert observed.collector_retry_contributed


def test_busy_lane_keeps_both_footer_halves_serial_and_preserves_evidence():
    reader = CardOcr.__new__(CardOcr); reader.engine = object()
    reader.parallel_footer_halves = True
    observations = iter([(['Pikachu'], [.99]), (['retreat'], [.98]),
                         (['35/108'], [.97]), (['35/109'], [.96])])
    reader._run = lambda image: next(observations)
    reader.region_reader = SimpleNamespace(engine=object(), _run=lambda image: pytest.fail('Busy lane'))
    reader.auxiliary_gate = AuxiliaryWorkGate()
    with ThreadPoolExecutor(max_workers=1) as executor, reader.auxiliary_gate.grading():
        reader.region_executor = executor
        result = reader.read(Image.new('RGB', (600, 840)))
    assert [h.text for h in result.hits] == ['Pikachu', 'retreat', '35/108', '35/109']
    assert all('parallel' not in p for p in result.passes)
    assert not result.failed and not reader.auxiliary_gate.active


def test_footer_schedule_failure_releases_lane_and_reads_both_patches_serially():
    from concurrent.futures import Future
    reader = CardOcr.__new__(CardOcr); reader.engine = object()
    reader.parallel_footer_halves = True
    reader.auxiliary_gate = AuxiliaryWorkGate()
    halves = iter([(['35/108'], [.98]), (['35/109'], [.97])])
    reader._run = lambda image: (['Pikachu'], [.99]) if image.width == 600 else next(halves)
    reader.region_reader = SimpleNamespace(engine=object(), _run=lambda image: (['retreat'], [.99]))
    class Executor:
        submitted = 0
        def submit(self, fn):
            self.submitted += 1
            if self.submitted == 2:
                raise RuntimeError('optional worker unavailable')
            future = Future(); future.set_result(fn()); return future
    reader.region_executor = Executor()
    result = reader.read(Image.new('RGB', (600, 840)))
    assert not result.failed and not reader.auxiliary_gate.active
    assert [h.text for h in result.hits] == ['Pikachu', 'retreat', '35/108', '35/109']
