"""Read-only distribution of an already validated phone-index candidate."""
from __future__ import annotations

import hashlib
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
# Optional fifth file: printings with the same picture as an index row, listed without a vector.
# Served only when the version file lists it; a version without it has exactly the four files.
_PRINTS = 'card_index.prints.tsv'
_HEX = re.compile(r'^[0-9a-f]{64}$')
_CACHE = 'public, max-age=31536000, immutable'
_MODEL_ID = '2ddf6ec79e37'
_candidates = OrderedDict()
_candidate_lock = RLock()
_extensions = OrderedDict()


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
    names = _NAMES + ((_PRINTS,) if (folder / _PRINTS).exists() or (folder / _PRINTS).is_symlink() else ())

    def signature():
        values = []
        for name in names:
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
    if (_PRINTS in names) != (_PRINTS in meta['files']):
        raise ValueError('prints file not listed in the version metadata')
    files = {}
    for name in names:
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


def _prefix_sha256(path: Path, length: int) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while length > 0:
            block = handle.read(min(length, 1 << 20))
            if not block:
                break
            digest.update(block)
            length -= len(block)
    return digest.hexdigest()


def _matches_snapshot(meta: dict, snapshot) -> bool:
    return (meta.get('catalogue_version') == snapshot.catalogue_version
            and meta.get('source_ids_sha256') == snapshot.ids_sha256
            and meta.get('source_embeddings_sha256') == snapshot.embeddings_sha256
            and meta.get('dims') == snapshot.embedding_dim
            and meta.get('model_id') == _MODEL_ID
            and meta.get('model_id') == str(snapshot.manifest.get('dinov2_sha256', ''))[:12])


def _extension_ok(root: Path, folder: Path, meta: dict, files: dict, snapshot) -> bool:
    """An index that extends a published one (version file `extends`) is served only if that base
    version still matches the loaded snapshot exactly, and this index's ids and vectors files
    start with the base's files byte for byte (its first rows are the snapshot's rows), followed
    by the added rows. The manifest's `rows` is this index's own row count."""
    ext = meta.get('extends')
    if not isinstance(ext, dict) or not isinstance(ext.get('version'), str) or ext['version'] == meta['version']:
        return False
    _, base_meta, base_files = _candidate(root, ext['version'])
    if ('extends' in base_meta or not _matches_snapshot(base_meta, snapshot)
            or base_meta.get('rows') != snapshot.indexed_count or ext.get('rows') != base_meta['rows']
            or base_meta.get('dims') != meta.get('dims') or base_meta.get('model_id') != meta.get('model_id')):
        return False
    rows = meta.get('rows')
    if not isinstance(rows, int) or rows <= base_meta['rows']:
        return False
    key = (str(folder), files['card_index.ids.txt']['sha256'], files['card_index.f16.bin']['sha256'],
           base_files['card_index.ids.txt']['sha256'], base_files['card_index.f16.bin']['sha256'])
    with _candidate_lock:
        if key in _extensions:
            return _extensions[key]
        ids_path, vectors_path = folder / 'card_index.ids.txt', folder / 'card_index.f16.bin'
        with ids_path.open('rb') as handle:
            lines = sum(block.count(b'\n') for block in iter(lambda: handle.read(1 << 20), b''))
        result = (lines == rows
                  and files['card_index.f16.bin']['bytes'] == rows * meta['dims'] * 2
                  and all(_prefix_sha256(folder / name, base_files[name]['bytes']) == base_files[name]['sha256']
                          for name in ('card_index.ids.txt', 'card_index.f16.bin')))
        _extensions[key] = result
        if len(_extensions) > 8:
            _extensions.popitem(last=False)
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
        folder, meta, files = _candidate(root, version)
        if 'extends' in meta:
            rows_ok = _extension_ok(root, folder, meta, files, snapshot)
        else:
            rows_ok = meta.get('rows') == snapshot.indexed_count
        if not _matches_snapshot(meta, snapshot) or not rows_ok:
            raise ValueError('candidate does not match the active snapshot')
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(503, 'Phone index unavailable') from None
    result = {'version': version, 'model_id': meta['model_id'],
              'catalogue_version': meta['catalogue_version'], 'rows': meta['rows'],
              'files': [{'name': name, **files[name],
                         'url': f'card-index/files/{version}/{name}'} for name in files]}
    return JSONResponse(result, headers={'Cache-Control': 'no-cache'})


@router.get('/card-index/files/{version}/{name}')
def file(request: Request, version: str, name: str):
    settings = _enabled(request)
    if name not in _NAMES and name != _PRINTS:
        raise HTTPException(404)
    try:
        folder, _, files = _candidate(settings.card_index_publish_dir, version)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(404) from None
    if name not in files:
        raise HTTPException(404)
    etag = '"' + files[name]['sha256'] + '"'
    headers = {'ETag': etag, 'Cache-Control': _CACHE, 'Accept-Ranges': 'bytes'}
    if request.headers.get('if-none-match') == etag and 'range' not in request.headers:
        return Response(status_code=304, headers=headers)
    return FileResponse(folder / name, headers=headers, media_type='application/octet-stream')
