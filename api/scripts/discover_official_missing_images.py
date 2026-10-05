"""Stage official image candidates; never mutate catalogue, mappings or vectors.

English asset paths are hypotheses until image/OCR/manual review. Japanese
sources require official detail-page set, number and name agreement. A missing
or ambiguous source is reported, not silently filled from a different printing.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'api'))
sys.path.insert(0, str(ROOT / 'catalogue'))
from bootstrap.catalogue import tpc_list_expansion, tpc_card_record, tpc_list_name

ALIASES = {'swsh12.5gg': 'SWSH12PT5GG', 'swsh4.5sv': 'SWSH45SV',
           'sm3.5': 'SM35', 'sm7.5': 'SM75', 'swshp': 'SWSHP', 'smp': 'SMP',
           'xyp': 'XYP', 'bwp': 'BWP', 'hgssp': 'HSP', 'sv03.5': 'SV3PT5'}


def english_urls(row):
    sid = row['set_id']
    if not re.fullmatch(r'(?:swsh|sm|sv|xy|bw|ex)\d+(?:\.\d+)?(?:gg|tg|sv)?|swshp|smp|svp|mep|xyp|bwp|hgssp', sid):
        return []
    code = ALIASES.get(sid, sid.upper().replace('.', 'PT'))
    collector = row['collector_number']
    if not re.fullmatch(r'[A-Za-z]*\d+', collector):
        return []
    tokens = [collector.upper()]
    if sid in {'svp', 'mep', 'swshp', 'smp', 'xyp', 'bwp', 'hgssp'}:
        prefix = {'svp': '', 'mep': '', 'swshp': 'SWSH', 'smp': 'SM', 'xyp': 'XY', 'bwp': 'BW', 'hgssp': 'HGSS'}[sid]
        number = int(re.search(r'\d+', collector).group())
        width = 2 if sid in {'smp', 'xyp', 'bwp', 'hgssp'} else 3
        tokens = [f'{prefix}{number:0{width}}', f'{prefix}{number}'] if prefix else [str(number)]
    return list(dict.fromkeys(f'https://assets.pokemon.com/{base}/img/cards/web/{code}/{code}_EN_{token}.png'
                             for base in ['assets/cms2', 'static-assets/content-assets/cms2'] for token in tokens))


def fetch_image(client, url, destination):
    if urlsplit(url).hostname not in {'assets.pokemon.com', 'www.pokemon-card.com'}:
        raise ValueError('Non-official image host')
    with client.stream('GET', url, follow_redirects=False) as response:
        if response.status_code in (404, 410):
            return None
        response.raise_for_status()
        if not response.headers.get('content-type', '').startswith('image/'):
            return None
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > 8_388_608:
                raise ValueError('Image size cap')
            chunks.append(chunk)
    payload = b''.join(chunks)
    with Image.open(io.BytesIO(payload)) as image:
        image.verify()
    with Image.open(io.BytesIO(payload)) as image:
        width, height = image.size
    if not (width >= 200 and height >= 280 and .60 < width / height < .80):
        raise ValueError('Not a usable portrait card image')
    with destination.open('xb') as handle:
        handle.write(payload)
    return {'image_url': url, 'file': destination.name,
            'sha256': hashlib.sha256(payload).hexdigest(), 'width': width, 'height': height}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--language', choices=['en', 'ja'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    image_dir = args.output / 'images'
    image_dir.mkdir()
    rows = [r for r in json.loads(args.inventory.read_text())['missing']
            if r['language'] == args.language]
    records = []
    with httpx.Client(timeout=12, follow_redirects=False, limits=httpx.Limits(max_connections=4)) as client:
        def probe_en(row):
            out = {**row, 'status': 'unresolved', 'attempts': []}
            for url in english_urls(row):
                try:
                    image = fetch_image(client, url, image_dir / (row['id'].replace(':', '_') + '.png'))
                    out['attempts'].append({'url': url, 'result': 'image' if image else 'absent'})
                    if image:
                        out.update(image, status='downloaded_unverified', identity_basis='asset-path hypothesis; review required')
                        break
                except (httpx.HTTPError, OSError, ValueError) as exc:
                    out['attempts'].append({'url': url, 'result': type(exc).__name__})
            return out
        if args.language == 'en':
            with ThreadPoolExecutor(max_workers=4) as pool:
                for i, out in enumerate(pool.map(probe_en, rows), 1):
                    records.append(out)
                    print(json.dumps({'progress': i, 'total': len(rows), 'id': out['id'], 'status': out['status']}), flush=True)
        else:
            grouped = {}
            for row in rows:
                grouped.setdefault(row['set_id'], []).append(row)
            for sid, wanted in grouped.items():
                found = {}
                errors = []
                try:
                    listed = tpc_list_expansion(client, sid)
                    names = {r['name'] for r in wanted}
                    items = [p for p in listed if tpc_list_name(p) in names]
                    def detail(item):
                        try:
                            return tpc_card_record(client, item)
                        except (httpx.HTTPError, ValueError):
                            return None
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        for record in pool.map(detail, items):
                            if record:
                                key = (record['set_id'].casefold(), record['collector'].lstrip('0') or '0', record['name'])
                                found.setdefault(key, {})[record['image_url']] = record
                except (httpx.HTTPError, ValueError) as exc:
                    errors.append(type(exc).__name__)
                for row in wanted:
                    out = {**row, 'status': 'unresolved', 'errors': errors}
                    key = (sid.casefold(), row['collector_number'].lstrip('0') or '0', row['name'])
                    matches = found.get(key, {})
                    if len(matches) == 1:
                        record = next(iter(matches.values()))
                        try:
                            image = fetch_image(client, record['image_url'], image_dir / (row['id'].replace(':', '_') + '.jpg'))
                            if image:
                                out.update(image, official_record=record, status='official_metadata_matched', identity_basis='official detail set + number + exact Japanese name')
                        except (httpx.HTTPError, OSError, ValueError) as exc:
                            out['errors'] = [*errors, type(exc).__name__]
                    elif len(matches) > 1:
                        out['status'] = 'ambiguous_official_prints'
                    records.append(out)
                (args.output / 'checkpoint.json').write_text(json.dumps({'records': records}, ensure_ascii=False))
                print(json.dumps({'set': sid, 'requested': len(wanted), 'official_exact_matches': sum(r['status']=='official_metadata_matched' for r in records if r['set_id']==sid), 'completed_rows': len(records), 'total': len(rows)}), flush=True)
    result = {'language': args.language, 'catalogue_mutated': False,
              'inventory_sha256': hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
              'records': records}
    (args.output / 'discovery.json').write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({'complete': True, 'rows': len(records), 'downloaded': sum('file' in r for r in records)}), flush=True)


if __name__ == '__main__':
    main()
