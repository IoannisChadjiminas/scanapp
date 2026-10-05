"""Paired extraction scorer: labels never participate in OCR or selection."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.ocr import pick_name_line


def normalize_name(value):
    # Formatting/HP suffix only; no fuzzy catalogue correction.
    value = unicodedata.normalize('NFKC', value or '')
    value = re.sub(r'(?i)\s*(?:HP\s*\d{1,3}|\d{1,3}\s*HP)\s*$', '', value)
    return ''.join(c for c in value.casefold() if c.isalnum())


def canonical_number(value):
    value = unicodedata.normalize('NFKC', value or '').upper().replace(' ', '').replace('-', '')
    parts = value.split('/')
    result = []
    for part in parts:
        match = re.fullmatch(r'([A-Z]{0,5})(\d{1,4})', part)
        if not match:
            return None
        result.append((match[1], str(int(match[2]))))
    return tuple(result)


def observed_numbers(lines):
    observed = []
    def add(value):
        parsed = canonical_number(value)
        if parsed and parsed not in observed:
            observed.append(parsed)
    for raw in lines:
        value = unicodedata.normalize('NFKC', raw).upper()
        for match in re.finditer(r'(?<!\d)((?:TG|GG|RC|SV)?\d{1,4})\s*/\s*((?:TG|GG|RC|SV)?\d{1,4})(?!\d)', value):
            add(match[0])
        for match in re.finditer(r'\b(?:SWSH|SVP|MEP|SM|XY|BW|HGSS|DP)\s*[- ]?\d{1,4}\b', value):
            add(match[0])
        if re.fullmatch(r'\s*#?\s*\d{1,4}\s*', value):
            add(value.replace('#', '').strip())
    # An explicitly printed SVP EN field adjacent to standalone digits.
    for code, digits in zip(lines, lines[1:]):
        if re.fullmatch(r'(?i)\s*(?:SVP|MEP)\s*(?:EN)?\s*', code) and re.fullmatch(r'\s*\d{3}\s*', digits):
            add(re.sub(r'(?i)\s|EN', '', code) + digits.strip())
    return observed


def agrees(observed, expected):
    return observed == expected if len(expected) == 2 else observed[0] == expected[0]


def stats(values):
    values = sorted(values)
    return dict(n=len(values), median_ms=round(statistics.median(values), 2),
                p95_ms=round(values[max(0, math.ceil(.95 * len(values)) - 1)], 2),
                max_ms=round(max(values), 2)) if values else None


def evaluate(record, truth):
    lines = [x['text'] for x in record['lines']]
    expected_name = normalize_name(truth.get('printed_name'))
    expected_number = canonical_number(truth.get('number'))
    numbers = observed_numbers(lines)
    predicted_name = pick_name_line(lines)
    name_recalled = bool(expected_name and any(expected_name in normalize_name(line) for line in lines))
    name_selected = None if not expected_name else normalize_name(predicted_name) == expected_name
    number_recalled = bool(expected_number and any(agrees(number, expected_number) for number in numbers))
    number_selected = None if not expected_number else bool(numbers and agrees(numbers[0], expected_number))
    return dict(name_recalled=name_recalled if expected_name else None, name_selected=name_selected,
                number_recalled=number_recalled if expected_number else None, number_selected=number_selected,
                predicted_name=predicted_name, observed_numbers=numbers, error=record.get('error'))


def aggregate(records):
    metrics = {}
    for field in ('name_recalled', 'name_selected', 'number_recalled', 'number_selected'):
        scores = [r['score'][field] for r in records if r['score'][field] is not None]
        metrics[field] = dict(correct=sum(scores), total=len(scores), percent=round(100 * sum(scores) / len(scores), 2)) if scores else None
    return dict(**metrics, latency=stats([r['ms'] for r in records if not r.get('first_for_script')]),
                errors=sum(bool(r.get('error')) for r in records))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--mlkit', type=Path, required=True)
    parser.add_argument('--server', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=2)
    args = parser.parse_args()
    labels = {r['id']:r for r in json.loads((args.audit / 'labels.json').read_text())}
    server = [json.loads(line) for line in args.server.read_text().splitlines()]
    mlkit_document = json.loads(args.mlkit.read_text())
    mlkit = mlkit_document['records']
    inputs = {(r['id'],r['profile']):r for r in json.loads((args.audit / 'inputs.json').read_text())}
    assert {(r['id'],r['profile']) for r in server} == set(inputs), 'Incomplete server run'
    assert len(server) == len(inputs), 'Duplicate server records'
    for round_number in range(args.rounds):
        repeated = [r for r in mlkit if r['round'] == round_number]
        assert {(r['id'],r['profile']) for r in repeated} == set(inputs), f'Incomplete ML Kit round {round_number}'
        assert len(repeated) == len(inputs), f'Duplicate ML Kit records in round {round_number}'
    assert len(mlkit) == len(inputs) * args.rounds, 'Unexpected ML Kit rounds'
    assert not any(r.get('error') for r in [*server, *mlkit]), 'Failed OCR call: do not publish a passing comparison'
    recognizer_ids = {script: set(r.get('recognizer_id') for r in mlkit if r['script'] == script)
                      for script in set(r['script'] for r in mlkit)}
    assert all(None not in ids and len(ids) == 1 for ids in recognizer_ids.values()), 'Unverified or changing native recognizers'
    assert len(set().union(*recognizer_ids.values())) == len(recognizer_ids), 'Native script instance IDs collided'
    records = []
    for record in [*server, *mlkit]:
        assert record['sha256'] == inputs[record['id'],record['profile']]['sha256']
        label = labels[record['id']]
        records.append(dict(**record, kind=label['truth']['kind'], language=label['truth']['language'],
                            source=label['source'], score=evaluate(record, label['truth'])))
    summary = dict(photos=len(labels), languages=dict(Counter(l['truth']['language'] for l in labels.values())),
                   mlkit_device=mlkit_document.get('device', 'iPhone 15 physical, iOS 27.0, profile build'),
                   server_device='Local Docker ARM64 CPU, limited to 2 vCPUs; not staging host', by_profile={}, strata={},
                   metrics_scope='Extraction only, not final scan accuracy. Name recall can include attack/evolution/holder text. Selected name uses the same generic selector without confidence for both engines. Number selection is first explicit number, not production ranking.',
                   limitations=['Convenience previously reviewed corpus; no unseen population claim.',
                                'Script supplied from frozen card language; automatic script selection untested.',
                                'Japanese printed name unavailable for one unsupported catalogue printing: name unscored, collector still scored.',
                                'Historical MOP023 annotation corrected to MEP023 using pre-existing pre-inference correction record.',
                                'Geometry cropping is identical and truth-independent but not the full production frame-selection pipeline.',
                                'iOS ML Kit confidence is null: never substitute a made-up 1.0 score.',
                                'Phone OCR times exclude input loading/writing; task_ms includes those costs. No upload timing.'])
    summary['run_integrity'] = dict(
        server_inputs=len(server), mlkit_inputs=len(mlkit), mlkit_rounds=args.rounds,
        errors=0, recognizer_ids={script: sorted(ids) for script, ids in recognizer_ids.items()},
        inputs_sha256=hashlib.sha256((args.audit / 'inputs.json').read_bytes()).hexdigest(),
        labels_sha256=hashlib.sha256((args.audit / 'labels.json').read_bytes()).hexdigest(),
        mlkit_results_file=args.mlkit.name, server_results_file=args.server.name,
        superseded_mlkit_run='mlkit-iphone15.json: Japanese native script instance was not verified; excluded',
    )
    summary['mlkit_cold_calls'] = [dict(script=r['script'], ms=r['ms'], task_ms=r.get('task_ms'))
                                  for r in mlkit if r.get('first_for_script')]
    for profile in ('full', 'card', 'title', 'footer'):
        summary['by_profile'][profile] = {engine:aggregate([r for r in records if r['engine']==engine and r['profile']==profile and r.get('round',0)==0])
                                         for engine in ('server_ppocr_v6','google_mlkit_ios')}
    for field in ('kind','language','source'):
        for value in sorted(set(r[field] for r in records)):
            summary['strata'][f'{field}:{value}'] = {profile:{engine:aggregate([r for r in records
                if r[field]==value and r['profile']==profile and r['engine']==engine and r.get('round',0)==0])
                for engine in ('server_ppocr_v6','google_mlkit_ios')} for profile in ('full','card','title','footer')}
    summary['mlkit_repeat_changes'] = []
    first = {(r['id'],r['profile']):r for r in records if r['engine']=='google_mlkit_ios' and r.get('round')==0}
    for r in records:
        if r['engine']=='google_mlkit_ios' and r.get('round')==1:
            old = first[r['id'],r['profile']]
            if [x['text'] for x in old['lines']] != [x['text'] for x in r['lines']]:
                summary['mlkit_repeat_changes'].append(dict(id=r['id'],profile=r['profile']))
    summary['mlkit_repeat_latency'] = {profile:stats([r['ms'] for r in mlkit if r['round'] == 1 and r['profile'] == profile])
                                      for profile in ('full','card','title','footer')}
    for engine in ('server_ppocr_v6','google_mlkit_ios'):
        summary.setdefault('primary_title_footer', {})[engine] = aggregate([r for r in records if r['engine']==engine
            and r['profile'] in ('title','footer') and r.get('round',0)==0])
    summary['paired_advantages'] = {}
    selected = {(r['engine'],r['id'],r['profile']):r for r in records if r.get('round',0)==0}
    # Retrieval evidence across all four profiles. This is an upper-bound
    # extraction experiment, not exact-printing confirmation or production UX.
    summary['any_profile_recall'] = {}
    for engine in ('server_ppocr_v6','google_mlkit_ios'):
        metrics = {}
        for field in ('name_recalled','number_recalled'):
            values = []
            for case_id in labels:
                scores = [selected[engine,case_id,profile]['score'][field] for profile in ('full','card','title','footer')]
                if any(score is not None for score in scores):
                    values.append(any(scores))
            metrics[field] = dict(correct=sum(values), total=len(values), percent=round(100 * sum(values) / len(values), 2)) if values else None
        summary['any_profile_recall'][engine] = metrics
    for profile in ('full','card','title','footer'):
        summary['paired_advantages'][profile] = {}
        for field in ('name_recalled','name_selected','number_recalled','number_selected'):
            outcome = Counter()
            for case_id in labels:
                a = selected['server_ppocr_v6',case_id,profile]['score'][field]
                b = selected['google_mlkit_ios',case_id,profile]['score'][field]
                if a is None or b is None:
                    continue
                outcome['both' if a and b else 'server_only' if a else 'mlkit_only' if b else 'neither'] += 1
            summary['paired_advantages'][profile][field] = dict(outcome)
    (args.audit / 'scored-records.json').write_text(json.dumps(records, ensure_ascii=False, indent=2))
    (args.audit / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
