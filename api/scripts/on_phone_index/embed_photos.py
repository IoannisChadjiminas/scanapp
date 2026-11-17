"""Query vectors for the gate photos, as the phone would search: card found and squared with the
server's detect_and_rectify, then DinoEmbedder.embed(crop, 'pad'), normalised.

    python -I embed_photos.py API_DIR MODEL WORK OUT_DIR SHARD [SHARD ...]
"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
api, model_path, work, out = sys.argv[1:5]
sys.path.insert(0, api)
from app.recognition.embed import DinoEmbedder
from app.recognition.detect import detect_and_rectify
work, out = Path(work), Path(out); out.mkdir(parents=True, exist_ok=True)
model = DinoEmbedder(model_path, 8, 1)
ids, vecs, meta = [], [], []
for shard in sys.argv[5:]:
    d = work / shard
    recs = json.load(open(next(d.glob('panel-*.json'))))
    for r in recs:
        with Image.open(d / 'photos' / r['photo_file']) as im:
            im = ImageOps.exif_transpose(im).convert('RGB')
            crop, found = detect_and_rectify(im)
            v = model.embed(crop, 'pad').astype(np.float32)
        ids.append(r['id']); vecs.append(v / np.linalg.norm(v))
        meta.append({'id': r['id'], 'shard': shard, 'found': bool(found), 'expected': r['expected_card_ids']})
    print(shard, len(recs), flush=True)
np.save(out / 'queries.npy', np.asarray(vecs, np.float32))
(out / 'queries.json').write_text(json.dumps(meta))
print('done', len(ids))
