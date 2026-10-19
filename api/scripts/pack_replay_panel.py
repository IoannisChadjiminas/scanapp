"""Pack a frozen photo panel into one folder for cpu_replay.py on another host.

Reads frozen cases (a JSON list, or JSONL rows with a "case" object such as
regression-cached.jsonl), finds each photo by its recorded repo path or, failing
that, by file name under --search folders, verifies its sha256, and copies it to
OUT/<photo_file>. Writes OUT/panel.json with only the fields the replay needs.
Nothing is downloaded; photos that cannot be found or fail the checksum are listed
and left out, never substituted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def load_cases(path):
    text = path.read_text()
    if text.lstrip().startswith('['):
        return json.loads(text)
    return [row.get('case', row) for row in map(json.loads, text.splitlines()) if row]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def find(case, repo_root, search):
    candidates = [repo_root / case['path']] if case.get('path') else []
    name = Path(case['photo_file']).name
    for folder in search:
        candidates += sorted(folder.rglob(name))
    for candidate in candidates:
        if candidate.is_file() and sha256(candidate) == case['sha256']:
            return candidate
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--cases', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=Path('.'))
    p.add_argument('--search', type=Path, action='append', default=[],
                   help='extra folder to look in by file name (repeatable)')
    p.add_argument('--exclude-kind', action='append', default=[],
                   help='leave out a case kind, e.g. reported_phone (repeatable)')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    panel, missing, excluded = [], [], []
    for case in load_cases(a.cases):
        if case['kind'] in a.exclude_kind:
            excluded.append(case['id'])
            continue
        source = find(case, a.repo_root, a.search)
        if source is None:
            missing.append(case['id'])
            continue
        target = a.out / case['photo_file']
        if not target.resolve().is_relative_to(a.out.resolve()):
            raise SystemExit(f'Unsafe photo_file for {case["id"]}')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        panel.append({k: case[k] for k in ('id', 'kind', 'expected_card_ids', 'photo_file', 'sha256')})
    (a.out / 'panel.json').write_text(json.dumps(panel, indent=1, ensure_ascii=False))
    print(json.dumps(dict(packed=len(panel), missing=missing, excluded=excluded)))


if __name__ == '__main__':
    main()
