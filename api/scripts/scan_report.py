"""Compare scans by the switches that were on, from server logs.

Reads `scan.diagnostics` log lines (for example `docker logs scanapp-api`)
and prints one block per `flags` combination: scan count, median and p90 per
stage, status mix, what users did with the result, quick-first-result timing,
and the phone's own stage times joined through the server scan id.

    docker logs --since 24h scanapp-api 2>&1 | python scripts/scan_report.py
    python scripts/scan_report.py api.log --json report.json
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import statistics
import sys

_PAIR = re.compile(r'(\w+)=(\S+)')
STAGES = ('total_ms', 'decode_ms', 'detect_ms', 'frame_proposal_ms', 'embed_ms',
          'retrieve_ms', 'local_artwork_ms', 'ocr_ms', 'grading_wait_ms', 'printing_review_ms')
PHONE_STAGES = ('preview', 'finalize', 'recognition')


def _fields(line: str, marker: str) -> dict[str, str] | None:
    at = line.find(marker + ' ')
    if at < 0:
        return None
    return dict(_PAIR.findall(line[at + len(marker):]))


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, 'none') else None
    except ValueError:
        return None


def parse(lines) -> dict[str, dict]:
    """scan id -> summary, outcome, stream and phone fields."""
    scans: dict[str, dict] = defaultdict(dict)
    phone_by_local: dict[str, dict[str, float]] = defaultdict(dict)
    local_to_server: dict[str, str] = {}
    for line in lines:
        if (row := _fields(line, 'scan_summary')) and row.get('scan_id'):
            scans[row['scan_id']]['summary'] = row
        elif (row := _fields(line, 'scan_outcome')) and row.get('scan_id'):
            # The last feedback on a scan is what the user settled on.
            scans[row['scan_id']]['outcome'] = row.get('outcome')
        elif (row := _fields(line, 'scan_stream_done')) and row.get('scan_id'):
            scans[row['scan_id']]['stream'] = row
        elif (row := _fields(line, 'phone')) and row.get('scan'):
            event, local = row.get('event', ''), row['scan']
            if row.get('server_scan'):
                local_to_server[local] = row['server_scan']
            stage, _, state = event.rpartition('.')
            if state == 'done' and stage in PHONE_STAGES and _float(row.get('elapsed_ms')) is not None:
                phone_by_local[local][f'phone_{stage}_ms'] = _float(row['elapsed_ms'])
            if event == 'recognition.provisional' and _float(row.get('elapsed_ms')) is not None:
                phone_by_local[local]['phone_first_result_ms'] = _float(row['elapsed_ms'])
            if event == 'queue.enqueued' and _float(row.get('bytes')) is not None:
                phone_by_local[local]['phone_bytes'] = _float(row['bytes'])
    for local, server in local_to_server.items():
        if server in scans:
            scans[server]['phone'] = phone_by_local.get(local, {})
    return {scan_id: row for scan_id, row in scans.items() if 'summary' in row}


def _spread(values: list[float]) -> dict | None:
    if not values:
        return None
    ordered = sorted(values)
    p90 = ordered[min(len(ordered) - 1, int(len(ordered) * .9))]
    return dict(n=len(values), median=round(statistics.median(values), 1), p90=round(p90, 1))


def report(scans: dict[str, dict]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in scans.values():
        groups[row['summary'].get('flags', 'none')].append(row)
    out = {}
    for flags, rows in sorted(groups.items(), key=lambda item: -len(item[1])):
        summaries = [r['summary'] for r in rows]
        outcomes = Counter(r.get('outcome') or 'no_feedback' for r in rows)
        given = sum(n for key, n in outcomes.items() if key != 'no_feedback')
        streams = [r['stream'] for r in rows if 'stream' in r]
        phone_keys = sorted({key for r in rows for key in r.get('phone', {})})
        out[flags] = dict(
            scans=len(rows),
            stages={stage: _spread([v for s in summaries if (v := _float(s.get(stage))) is not None])
                    for stage in STAGES},
            embeddings=_spread([v for s in summaries if (v := _float(s.get('embeddings'))) is not None]),
            upload_bytes=_spread([v for s in summaries if (v := _float(s.get('bytes'))) is not None]),
            status=dict(Counter(s.get('status', 'none') for s in summaries)),
            footer_skipped=sum(s.get('footer_skipped') == 'true' for s in summaries),
            outcomes=dict(outcomes),
            confirmed_rate=round(outcomes['confirmed'] / given, 3) if given else None,
            corrected_rate=round(outcomes['corrected'] / given, 3) if given else None,
            stream=dict(
                provisional_ms=_spread([v for s in streams if (v := _float(s.get('provisional_ms'))) is not None]),
                final_ms=_spread([v for s in streams if (v := _float(s.get('final_ms'))) is not None]),
                agrees=sum(s.get('agrees') == 'true' for s in streams),
                disagrees=sum(s.get('agrees') == 'false' for s in streams),
            ) if streams else None,
            phone={key: _spread([r['phone'][key] for r in rows if key in r.get('phone', {})])
                   for key in phone_keys},
        )
    return out


def render(result: dict[str, dict]) -> str:
    lines = []
    for flags, row in result.items():
        lines.append(f'== flags: {flags}  ({row["scans"]} scans)')
        for stage, spread in row['stages'].items():
            if spread:
                lines.append(f'   {stage:<20} median {spread["median"]:>8}  p90 {spread["p90"]:>8}  n={spread["n"]}')
        if row['embeddings']:
            lines.append(f'   embeddings           median {row["embeddings"]["median"]:>8}')
        if row['upload_bytes']:
            lines.append(f'   upload bytes         median {row["upload_bytes"]["median"]:>8}')
        lines.append(f'   status   {row["status"]}')
        lines.append(f'   feedback {row["outcomes"]}  confirmed {row["confirmed_rate"]}  '
                     f'corrected {row["corrected_rate"]}')
        if row['stream']:
            s = row['stream']
            lines.append(f'   stream   first {s["provisional_ms"]}  final {s["final_ms"]}  '
                         f'agrees {s["agrees"]}  disagrees {s["disagrees"]}')
        for key, spread in row['phone'].items():
            if spread:
                lines.append(f'   {key:<20} median {spread["median"]:>8}  p90 {spread["p90"]:>8}  n={spread["n"]}')
    return '\n'.join(lines) or 'No scan_summary lines found.'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('logs', nargs='*', type=Path, help='log files; stdin when omitted')
    parser.add_argument('--json', type=Path, help='also write the report as JSON')
    args = parser.parse_args()
    if args.logs:
        lines = [line for path in args.logs for line in path.read_text(errors='replace').splitlines()]
    else:
        lines = sys.stdin.read().splitlines()
    result = report(parse(lines))
    print(render(result))
    if args.json:
        args.json.write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
