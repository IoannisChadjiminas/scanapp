"""Read-only distribution of an already validated phone-index candidate."""
from __future__ import annotations

import json
import re
from collections import OrderedDict
from threading import RLock
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from app.recognition.artifacts import sha256_file

router = APIRouter()
_NAMES = ('card_index.f16.bin', 'card_index.ids.txt', 'card_index.meta.tsv', 'card_index.version.json')
_HEX = re.compile(r'^[0-9a-f]{64}$')
_CACHE = 'public, max-age=31536000, immutable'
_MODEL_ID = '2ddf6ec79e37'
_candidates = OrderedDict()
_candidate_lock = RLock()


def _candidate(root: Path, version: str) -> tuple[Path, dict, dict]:
    with _candidate_lock:
        return _checked_candidate(root, version)


def _checked_candidate(root: Path, version: str) -> tuple[Path, dict, dict]:
    if not _HEX.fullmatch(version):
        raise ValueError('invalid version')
    root = root.resolve()
    if (root / version).is_symlink():
        raise ValueError('invalid folder')
    folder = (root / version).resolve()
    if folder.parent != root or not folder.is_dir():
        raise ValueError('invalid folder')
    def signature():
        values = []
        for name in _NAMES:
            path = folder / name
            if path.is_symlink() or not path.is_file():
                raise ValueError('missing file')
            stat = path.stat()
            values.append((stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino))
        return tuple(values)

    stamp = signature()
    key = str(folder)
    cached = _candidates.get(key)
    if cached is not None and cached[0] == stamp:
        _candidates.move_to_end(key)
        return cached[1]
    _candidates.pop(key, None)
    meta = json.loads((folder / _NAMES[3]).read_text())
    if not isinstance(meta, dict) or meta.get('version') != version or not isinstance(meta.get('files'), dict):
        raise ValueError('invalid version metadata')
    files = {}
    for name in _NAMES:
        file = folder / name
        if file.is_symlink() or not file.is_file():
            raise ValueError('missing file')
        info = {'bytes': file.stat().st_size, 'sha256': sha256_file(file)}
        if name != _NAMES[3] and meta['files'].get(name) != info:
            raise ValueError('invalid file checksum')
        files[name] = info
    if signature() != stamp:
        raise ValueError('candidate changed during validation')
    result = folder, meta, files
    _candidates[key] = (stamp, result)
    if len(_candidates) > 32:
        _candidates.popitem(last=False)
    return result


def _enabled(request: Request):
    settings = request.app.state.settings
    if not settings.card_index_publish:
        raise HTTPException(404)
    return settings


@router.get('/card-index/manifest')
def manifest(request: Request):
    settings = _enabled(request)
    snapshot = request.app.state.runtime.snapshot
    if snapshot is None:
        raise HTTPException(503, 'Recognition snapshot unavailable')
    try:
        root = settings.card_index_publish_dir
        version = (root / 'ACTIVE').read_text().strip()
        _, meta, files = _candidate(root, version)
        if (meta.get('catalogue_version') != snapshot.catalogue_version
                or meta.get('source_ids_sha256') != snapshot.ids_sha256
                or meta.get('source_embeddings_sha256') != snapshot.embeddings_sha256
                or meta.get('rows') != snapshot.indexed_count
                or meta.get('dims') != snapshot.embedding_dim
                or meta.get('model_id') != _MODEL_ID
                or meta.get('model_id') != str(snapshot.manifest.get('dinov2_sha256', ''))[:12]):
            raise ValueError('candidate does not match the active snapshot')
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(503, 'Phone index unavailable') from None
    result = {'version': version, 'model_id': meta['model_id'],
              'catalogue_version': meta['catalogue_version'], 'rows': meta['rows'],
              'files': [{'name': name, **files[name],
                         'url': f'card-index/files/{version}/{name}'} for name in _NAMES]}
    return JSONResponse(result, headers={'Cache-Control': 'no-cache'})


@router.get('/card-index/files/{version}/{name}')
def file(request: Request, version: str, name: str):
    settings = _enabled(request)
    if name not in _NAMES:
        raise HTTPException(404)
    try:
        folder, _, files = _candidate(settings.card_index_publish_dir, version)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(404) from None
    etag = '"' + files[name]['sha256'] + '"'
    headers = {'ETag': etag, 'Cache-Control': _CACHE, 'Accept-Ranges': 'bytes'}
    if request.headers.get('if-none-match') == etag and 'range' not in request.headers:
        return Response(status_code=304, headers=headers)
    return FileResponse(folder / name, headers=headers, media_type='application/octet-stream')
