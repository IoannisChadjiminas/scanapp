"""Read-only distribution of the phone's daily price file (app/phone_prices.py)."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from app.phone_prices import FILE_NAME, read_active, read_version

router = APIRouter()
_CACHE = 'public, max-age=31536000, immutable'


def _enabled(request: Request):
    settings = request.app.state.settings
    if not settings.card_prices_publish:
        raise HTTPException(404)
    return settings


@router.get('/card-prices/manifest')
def manifest(request: Request):
    settings = _enabled(request)
    try:
        _, meta = read_active(settings.card_prices_dir)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        # Not built yet (no phone index or no price file): phones keep theirs.
        raise HTTPException(404) from None
    version = meta['version']
    result = {'version': version, 'guide_date': meta.get('guide_date'), 'rows': meta['rows'],
              'priced': meta.get('priced'), 'index_version': meta.get('index_version'),
              'file': {'name': FILE_NAME, 'bytes': meta['file']['bytes'], 'sha256': meta['file']['sha256'],
                       'url': f'card-prices/files/{version}/{FILE_NAME}'}}
    return JSONResponse(result, headers={'Cache-Control': 'no-cache'})


@router.get('/card-prices/files/{version}/{name}')
def file(request: Request, version: str, name: str):
    settings = _enabled(request)
    if name != FILE_NAME:
        raise HTTPException(404)
    try:
        folder, meta = read_version(settings.card_prices_dir, version)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(404) from None
    etag = '"' + meta['file']['sha256'] + '"'
    headers = {'ETag': etag, 'Cache-Control': _CACHE}
    if request.headers.get('if-none-match') == etag:
        return Response(status_code=304, headers=headers)
    # Sent as stored: the phone checks the gzip bytes' sha256, then unzips.
    return FileResponse(folder / name, headers=headers, media_type='application/octet-stream')
