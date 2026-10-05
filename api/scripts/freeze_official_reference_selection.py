"""Freeze identity-approved references and an explicit unresolved coverage queue."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.artifacts import sha256_file


def main():
    root = Path(__file__).resolve().parents[2]
    recovery = root / 'data/image-recovery/20261002-official'
    decisions = json.loads((root / 'docs/official-reference-manual-decisions-20261002.json').read_text())
    evidence = {}
    provenance = []
    for shard in ('a', 'b', 'c'):
        audit = recovery / f'en/identity-audit-{shard}.json'
        discovery = recovery / 'en/discovery.json'
        data = json.loads(audit.read_text())
        if data['discovery_sha256'] != sha256_file(discovery):
            raise ValueError('English audit discovery changed')
        for row in data['records']:
            if row['card_id'] in evidence:
                raise ValueError('Duplicate English audit ID')
            evidence[row['card_id']] = row
        index = recovery / f'en/review-{shard}/index.json'
        sheets = json.loads(index.read_text())
        approved = set(decisions['approved_sheets'][shard])
        if approved != {s['file'] for s in sheets}:
            raise ValueError('Incomplete visual review')
        for sheet in sheets:
            provenance.append({'file': str((index.parent / sheet['file']).relative_to(root)),
                               'sha256': sha256_file(index.parent / sheet['file']),
                               'card_ids': sheet['card_ids']})
            for card_id in sheet['card_ids']:
                if card_id not in decisions['rejected_card_ids']:
                    evidence[card_id] = {**evidence[card_id], 'status': 'manual_visual'}
    accepted, pending, languages = [], [], {}
    for language, folder in [('en', 'en'), ('ja', 'ja-corrected')]:
        discovery = recovery / folder / 'discovery.json'
        rows = json.loads(discovery.read_text())['records']
        languages[language] = {'audited_missing': len(rows), 'recovered': 0, 'pending': 0}
        for row in rows:
            verification = evidence.get(row['id'], {}).get('status') if language == 'en' else row['status']
            if 'file' in row and verification in {'manual_visual', 'ocr_corroborated', 'official_metadata_matched'}:
                path = discovery.parent / 'images' / row['file']
                if sha256_file(path) != row['sha256']:
                    raise ValueError('Reference bytes changed')
                if language == 'en' and evidence[row['id']]['image_sha256'] != row['sha256']:
                    raise ValueError('Reference no longer matches audit')
                if language == 'ja':
                    official = row['official_record']
                    if (official['name'] != row['name'] or official['set_id'].casefold() != row['set_id'].casefold()
                        or (official['collector'].lstrip('0') or '0') != (row['collector_number'].lstrip('0') or '0')
                        or official['image_url'] != row['image_url']):
                        raise ValueError('Japanese official identity mismatch')
                accepted.append({**row, 'verification': verification,
                                 'source_file': '/workspace/' + str(path.relative_to(root))})
                languages[language]['recovered'] += 1
            else:
                pending.append({**row, 'recovery_status': 'pending_source_or_identity_review'})
                languages[language]['pending'] += 1
    selection = recovery / 'selection.json'
    if selection.exists():
        raise ValueError('Selection already frozen')
    selection.write_text(json.dumps({'records': accepted, 'manual_sheet_evidence': provenance,
                                    'mappings_mutated': False}, indent=2, ensure_ascii=False))
    (recovery / 'coverage-audit.json').write_text(json.dumps({'languages': languages,
        'recovered': len(accepted), 'pending': pending,
        'other_languages': 'Chinese inventoried separately; not searched in this EN/JA pass',
        'scope': 'official-host search pass, not proof unresolved images do not exist elsewhere'}, indent=2, ensure_ascii=False))
    print(json.dumps(languages))


if __name__ == '__main__':
    main()
