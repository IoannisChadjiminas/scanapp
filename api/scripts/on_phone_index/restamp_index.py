"""Re-stamp published phone-index versions for a new catalogue_version (same rows and vectors).

    python3 restamp_index.py PUBLISH_DIR NEW_CATALOGUE_VERSION_FILE BASE V4 VARIANT

Writes three new folders (base, extension, model variant) next to the old ones, each named by its
recomputed version, and prints the new versions. Old folders and ACTIVE pointers are not touched.
"""
import hashlib, json, os, shutil, sys
from pathlib import Path

root, new_cv = Path(sys.argv[1]), Path(sys.argv[2]).read_text().strip()
base_v, v4_v, var_v = sys.argv[3:6]

def h_compact(idn):  # export_index.py / extend_index.py
    return hashlib.sha256(json.dumps(idn, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def h_default(idn):  # the run-4 model variant (tests/_other_model)
    return hashlib.sha256(json.dumps(idn, sort_keys=True).encode()).hexdigest()

def scheme(meta):
    idn = {k: v for k, v in meta.items() if k != 'version'}
    for f in (h_compact, h_default):
        if f(idn) == meta['version']:
            return f
    raise SystemExit(f"cannot reproduce version {meta['version']}")

def restamp(old, change, ensure_ascii):
    src = root / old
    meta = json.loads((src / 'card_index.version.json').read_text())
    assert meta['version'] == old
    f = scheme(meta)
    assert meta['catalogue_version'] != new_cv
    meta.pop('version')
    meta['catalogue_version'] = new_cv
    change(meta)
    meta['version'] = f({k: v for k, v in meta.items() if k != 'version'})
    dst = root / meta['version']
    assert not dst.exists(), dst
    tmp = root / f".tmp-{meta['version']}"
    tmp.mkdir()
    for name in meta['files']:
        shutil.copy2(src / name, tmp / name)
        assert hashlib.sha256((tmp / name).read_bytes()).hexdigest() == meta['files'][name]['sha256'], name
    (tmp / 'card_index.version.json').write_text(json.dumps(meta, sort_keys=True, ensure_ascii=ensure_ascii) + '\n', encoding='utf-8')
    os.chmod(tmp, 0o755)
    for p in tmp.iterdir():
        os.chmod(p, 0o644)
    tmp.rename(dst)
    return meta['version']

nb = restamp(base_v, lambda m: None, True)
n4 = restamp(v4_v, lambda m: m['extends'].update(version=nb), False)
nv = restamp(var_v, lambda m: m.update(variant_of=n4), False)
print(json.dumps({"base": nb, "v4": n4, "variant": nv}))
