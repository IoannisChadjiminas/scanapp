"""The replay script maps its switches to the stage 1 / 1b flags; the twin guard is one of them."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

_SPEC = importlib.util.spec_from_file_location(
    'android_fastpath_replay', Path(__file__).resolve().parents[1] / 'scripts' / 'android_fastpath_replay.py')
replay = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(replay)

OFF = dict(number_repair=False, fuzzy_name=False, server_frame=False, twin_guard=False)


def test_no_switch_turns_nothing_on():
    assert replay.replay_extra(SimpleNamespace(**OFF)) == {}


def test_twin_guard_switch_maps_to_stage1_twin_guard():
    assert replay.replay_extra(SimpleNamespace(**{**OFF, 'twin_guard': True})) == {'stage1_twin_guard': True}


def test_staging_set_maps_each_switch_to_its_flag():
    args = SimpleNamespace(**{**OFF, 'number_repair': True, 'server_frame': True, 'twin_guard': True})
    assert replay.replay_extra(args) == {
        'stage1_number_repair': True, 'stage1b_server_frame': True, 'stage1_twin_guard': True}
