"""Compare cpu_replay.py outputs: CPU per scan, latency, and exact-match changes."""
import json
from pathlib import Path
import sys


def load(path):
    return {r['id']: r for r in map(json.loads, Path(path).read_text().splitlines()) if r}


def quantile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def correct(row):
    expected = row['expected']
    return None if not expected else norm_card(row['card_id']) in expected


def norm_card(card_id):
    """The API returns the same English card as 'sv01-203' or 'en:sv01-203'; treat them as equal."""
    return 'en:' + card_id if card_id and ':' not in card_id else card_id


def identity(row):
    ocr, grading = row['ocr'] or {}, row['grading'] or {}
    return dict(card=norm_card(row['card_id']), status=row['status'], printing=row['printing'],
                name=ocr.get('name_text'), collector=ocr.get('collector_text'),
                graded=grading.get('is_graded'), company=grading.get('company'),
                grade=grading.get('grade'))


def summarise(name, rows):
    cpu = [r['cpu_ms'] for r in rows.values()]
    wall = [r['http_ms'] for r in rows.values()]
    ok = [correct(r) for r in rows.values() if correct(r) is not None]
    return dict(config=name, scans=len(rows), cpu_ms_mean=sum(cpu) / len(cpu),
        cpu_ms_p50=quantile(cpu, .5), cpu_ms_p90=quantile(cpu, .9),
        http_ms_p50=quantile(wall, .5), http_ms_p90=quantile(wall, .9),
        correct=f'{sum(ok)}/{len(ok)}', errors=sum(r['http'] != 200 for r in rows.values()))


def main(base_path, *variant_paths):
    base = load(base_path)
    out = [summarise('baseline', base)]
    for path in variant_paths:
        rows = load(path)
        summary = summarise(Path(path).stem, rows)
        changes = []
        for key, row in rows.items():
            if key in base and identity(row) != identity(base[key]):
                before, after = identity(base[key]), identity(row)
                changes.append(dict(id=key, kind=row['kind'],
                    fields={k: [before[k], after[k]] for k in before if before[k] != after[k]}))
        answer = [c for c in changes if 'card' in c['fields'] or 'status' in c['fields']]
        summary['answer_changes'] = len(answer)
        summary['answer_changed_ids'] = [c['id'] for c in answer]
        summary['regressions'] = [k for k, row in rows.items() if k in base
                                  and correct(base[k]) and correct(row) is False]
        summary['fixes'] = [k for k, row in rows.items() if k in base
                            and correct(base[k]) is False and correct(row)]
        summary['cpu_saved_pct'] = 100 * (1 - summary['cpu_ms_mean'] / out[0]['cpu_ms_mean'])
        summary['exact_match_changes'] = len(changes)
        summary['changes'] = changes
        out.append(summary)
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main(*sys.argv[1:])
