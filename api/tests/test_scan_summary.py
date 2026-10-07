import json
import sqlite3
from types import SimpleNamespace

from app.config import Settings
from app.scan_summary import scan_flags, scan_outcome, scan_outcome_line, scan_summary_line
from scripts import export_labels, replay_thresholds, scan_report


def response(**timings):
    top = SimpleNamespace(card_id='swsh1-1', visual_score=.91)
    runner = SimpleNamespace(card_id='swsh1-2', visual_score=.80)
    return SimpleNamespace(id='scan-1', status=SimpleNamespace(value='matched'),
                           match_state='matched', suggestions=[top, runner],
                           timings_ms={'total_ms': 2345.67, 'ocr_ms': 900., 'embeddings': 2.,
                                       'ocr_passes_count': 1., **timings})


def test_flags_list_switches_that_are_on_and_what_the_request_asked():
    settings = Settings(_env_file=None, scan_stream_results=True, grading_requires_client_hint=False,
                        ocr_title_only_single_printing=True)
    flags = scan_flags(settings, stream=True, skip_detect=True, graded=False)
    assert 'scan_stream_results' in flags and 'ocr_title_only_single_printing' in flags
    assert 'grading_requires_client_hint' not in flags
    assert flags[-3:] == ['req_stream', 'req_skip_detect', 'req_graded_false']


def test_summary_line_carries_scores_stages_and_flags():
    line = scan_summary_line(response(ocr_footer_skipped=1.), Settings(_env_file=None),
                             trace='t1', upload_bytes=812345, flags=['req_stream'])
    assert line.startswith('scan_summary trace=t1 scan_id=scan-1 status=matched')
    for part in ('top=swsh1-1', 'visual=0.9', 'gap=0.110', 'total_ms=2345.7', 'ocr_ms=900.0',
                 'embeddings=2', 'ocr_passes=1', 'footer_skipped=true', 'bytes=812345',
                 'thresholds=0.78/0.70/0.04', 'flags=req_stream'):
        assert part in line.split(), part


def test_outcome_says_whether_the_user_kept_the_top_card():
    ranking = json.dumps([{'card_id': 'a'}, {'card_id': 'b'}])
    assert scan_outcome('confirm', 'a', ranking) == 'confirmed'
    assert scan_outcome('confirm', 'b', ranking) == 'corrected'
    assert scan_outcome('correct', 'b', ranking) == 'corrected'
    assert scan_outcome('reject', None, ranking) == 'rejected'
    assert 'outcome=confirmed' in scan_outcome_line('s', action='confirm', chosen='a',
                                                    status='matched', combined_ranking_json=ranking)


def test_report_groups_by_flags_and_joins_feedback_stream_and_phone():
    settings = Settings(_env_file=None)
    logs = [
        'INFO scan.diagnostics ' + scan_summary_line(response(), settings, trace='t', upload_bytes=10,
                                                     flags=['req_stream']),
        'INFO scan.diagnostics scan_stream_done trace=t scan_id=scan-1 provisional_ms=1600.0 '
        'final_ms=6900.0 provisional_top=swsh1-1 final_top=swsh1-1 agrees=true',
        'INFO scan.diagnostics phone event=queue.enqueued scan=local-1 bytes=900000',
        'INFO scan.diagnostics phone event=recognition.done scan=local-1 elapsed_ms=7100',
        'INFO scan.diagnostics phone event=scan.result scan=local-1 status=matched server_scan=scan-1',
        'INFO scan.diagnostics scan_outcome scan_id=scan-1 action=confirm outcome=confirmed '
        'status=matched chosen=swsh1-1',
        'INFO scan.diagnostics ' + scan_summary_line(SimpleNamespace(**{**vars(response()), 'id': 'scan-2'}),
                                                     settings, trace='u', upload_bytes=20, flags=[]),
    ]
    result = scan_report.report(scan_report.parse(logs))
    assert set(result) == {'req_stream', 'none'}
    streamed = result['req_stream']
    assert streamed['scans'] == 1 and streamed['confirmed_rate'] == 1.0
    assert streamed['stream']['provisional_ms']['median'] == 1600.0 and streamed['stream']['agrees'] == 1
    assert streamed['phone']['phone_recognition_ms']['median'] == 7100.0
    assert streamed['phone']['phone_bytes']['median'] == 900000.0
    assert result['none']['outcomes'] == {'no_feedback': 1}
    assert 'flags: req_stream' in scan_report.render(result)


def labelled_db():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE scans (id TEXT, created_at TEXT, status TEXT, threshold_config_json TEXT, '
                 'combined_ranking_json TEXT, confirmed_card_id TEXT, rejected INTEGER)')
    def ranking(top, visual, second=.50):
        return json.dumps([{'card_id': top, 'visual_score': visual, 'ocr_text': 'private'},
                           {'card_id': 'other', 'visual_score': second}])
    rows = [('right-high', 'matched', ranking('a', .90), 'a', 0),
            ('right-mid', 'uncertain', ranking('b', .75), 'b', 0),
            ('wrong-mid', 'uncertain', ranking('c', .74), 'z', 0),
            ('rejected', 'uncertain', ranking('d', .72), None, 1),
            ('no-feedback', 'matched', ranking('e', .95), None, 0)]
    for scan_id, status, combined, chosen, rejected in rows:
        conn.execute('INSERT INTO scans VALUES (?,?,?,?,?,?,?)',
                     (scan_id, '2026-10-07T00:00:00', status, '{}', combined, chosen, rejected))
    return conn


def test_export_keeps_only_scans_with_feedback_and_no_private_fields():
    labels = list(export_labels.labelled_rows(labelled_db()))
    assert [row['scan_id'] for row in labels] == ['right-high', 'right-mid', 'wrong-mid', 'rejected']
    assert [row['outcome'] for row in labels] == ['confirmed', 'confirmed', 'corrected', 'rejected']
    assert all('ocr_text' not in item for row in labels for item in row['ranking'])


def test_replay_finds_the_widest_threshold_that_keeps_precision():
    labels = list(export_labels.labelled_rows(labelled_db()))
    today = replay_thresholds.score(labels, min_visual=.78, min_visual_ocr=.70, min_gap=.04)
    assert (today['matched'], today['correct'], today['precision']) == (1, 1, 1.0)
    rows = replay_thresholds.sweep(labels, visual=[.70, .745, .78], visual_ocr=[.70], gap=[.04])
    chosen = replay_thresholds.best(rows, .99)
    # .745 adds the correct .75 scan; .70 would also match the wrong and rejected ones.
    assert chosen['min_visual'] == .745 and chosen['coverage'] == .5
