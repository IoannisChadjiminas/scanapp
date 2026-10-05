"""Download only explicitly selected public URLs for a private diagnostic pilot."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import httpx
from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=1, choices=range(1,5))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads(args.manifest.read_text())
    downloaded = []
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        def download(photo):
            if not re.fullmatch(r'[a-z0-9_]+', photo['id']):
                raise ValueError('Unsafe photo ID')
            url = urlsplit(photo['image_url'])
            if url.scheme != 'https' or url.hostname not in {'i.ebayimg.com', 'i.etsystatic.com'}:
                raise ValueError('Unexpected public image host')
            record = dict(photo)
            path = args.output / (photo['id'] + '.jpg')
            try:
                digest = hashlib.sha256()
                with client.stream('GET', photo['image_url']) as response:
                    response.raise_for_status()
                    if not response.headers.get('content-type', '').startswith('image/'):
                        raise ValueError('Response is not an image')
                    size = 0
                    with path.open('xb') as handle:
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > 12_582_912:
                                raise ValueError('Photo exceeds download cap')
                            digest.update(chunk)
                            handle.write(chunk)
                with Image.open(path) as image:
                    image.verify()
                record.update(path=str(path), sha256=digest.hexdigest(), bytes=size,
                              download_status='downloaded')
            except (httpx.HTTPError, OSError, ValueError) as exc:
                record.update(download_status='unavailable', error=type(exc).__name__)
            print(json.dumps({'id':record['id'], 'status':record['download_status']}), flush=True)
            return record
        # Distinct files; bounded public-host concurrency, deterministic order.
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            downloaded = list(executor.map(download, manifest['photos']))
    (args.output / 'downloads.json').write_text(json.dumps({'photos':downloaded}, indent=2))


if __name__ == '__main__':
    main()
