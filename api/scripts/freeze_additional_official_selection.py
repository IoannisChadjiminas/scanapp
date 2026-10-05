"""Freeze the second official EN pass without overwriting the first audit."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.artifacts import sha256_file

root = Path(__file__).resolve().parents[2]
recovery = root / 'data/image-recovery/20261002-official'
folder = recovery / 'en-additional'
decisions = json.loads((root / 'docs/official-reference-additional-manual-decisions-20261002.json').read_text())
sheets = json.loads((folder / 'review/index.json').read_text())
if set(decisions['approved_sheets']) != {s['file'] for s in sheets}:
    raise ValueError('Incomplete supplemental review')
seen = {i for s in sheets for i in s['card_ids']}
pending_ids = set(decisions['pending_card_ids'])
records, pending = [], []
for row in json.loads((folder / 'discovery.json').read_text())['records']:
    if 'file' in row and row['id'] in seen and row['id'] not in pending_ids:
        path = folder / 'images' / row['file']
        if sha256_file(path) != row['sha256']:
            raise ValueError('Supplemental reference checksum changed')
        records.append({**row, 'verification': 'manual_visual',
                        'source_file': '/workspace/' + str(path.relative_to(root))})
    else:
        pending.append({**row, 'recovery_status': 'pending_visual_identifier_review' if row['id'] in pending_ids
                        else 'pending_source_or_identity_review'})
selection = recovery / 'selection-additional.json'
if selection.exists():
    raise ValueError('Supplemental selection already frozen')
selection.write_text(json.dumps({'records': records, 'sheet_evidence': [
    {**s, 'sha256': sha256_file(folder / 'review' / s['file'])} for s in sheets]}, indent=2, ensure_ascii=False))
first = json.loads((recovery / 'selection.json').read_text())['records']
combined = first + records
if len({r['id'] for r in combined}) != len(combined):
    raise ValueError('Recovery selections overlap')
(recovery / 'selection-combined.json').write_text(json.dumps({'records': combined}, indent=2, ensure_ascii=False))
initial = json.loads((recovery / 'coverage-audit.json').read_text())
pending += [r for r in initial['pending'] if r['language'] != 'en']
languages = initial['languages']
languages['en']['recovered'] += len(records)
languages['en']['pending'] = sum(r['language'] == 'en' for r in pending)
(recovery / 'coverage-audit-final.json').write_text(json.dumps({**initial, 'languages': languages,
    'recovered': len(combined), 'pending': pending, 'supplemental_recovered': len(records)}, indent=2, ensure_ascii=False))
print(json.dumps({'languages': languages, 'additional': len(records), 'total': len(combined)}))
