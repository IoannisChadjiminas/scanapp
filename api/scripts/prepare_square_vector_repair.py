"""Prepare the single proven missing square vector; preserve all parent bytes."""
import argparse
import base64
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.recognition.embed import DinoEmbedder
from catalogue_completion_inventory import digest_file


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--export',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    parent=None;manifest=None;vectors={};pad=None
    for line in gzip.open(a.export,'rt'):
        r=json.loads(line);row=r.get('row',{})
        if r['table']=='import_manifest':parent=row
        if r['table']=='reference_metadata' and row['source_key']=='vector-manifest:square':manifest=row['metadata']
        if r['table']=='card_embeddings':
            if row['mode']=='square':vectors[row['card_id']]=row
            if row['mode']=='pad' and row['card_id']=='en:mep-078':pad=row
    evidence=parent['metadata']['reference_recovery']['reference']
    if evidence['id']!='en:mep-078' or evidence['verification']!='manual_visual':
        raise ValueError('Expected approved exact reference')
    if digest_file(a.source)!=evidence['sha256'] or digest_file(a.model)!=manifest['dinov2_sha256']:
        raise ValueError('Source/model hash mismatch')
    if evidence['id'] in vectors or not pad:
        raise ValueError('Live coverage changed')
    old_ids=manifest['indexed_ids']
    if set(old_ids)!=vectors.keys():raise ValueError('Parent membership mismatch')
    matrix=np.array([np.frombuffer(base64.b64decode(vectors[c]['embedding']['base64'])[4:],dtype='>f4').astype(np.float32) for c in old_ids])
    parent_npy=a.output/'parent-embeddings.npy';np.save(parent_npy,matrix)
    if digest_file(parent_npy)!=manifest['embeddings_sha256']:
        raise ValueError('Parent NPY reconstruction mismatch')
    model=DinoEmbedder(str(a.model),1,1)
    with Image.open(a.source) as image:
        dimensions=image.size
        vector=model.embed(image,'square')
        replay=model.embed(image,'pad')
    prior_pad=np.frombuffer(base64.b64decode(pad['embedding']['base64'])[4:],dtype='>f4').astype(np.float32)
    if not np.allclose(prior_pad,replay,rtol=1e-4,atol=1e-5):
        raise ValueError('Pinned source/model pad replay mismatch')
    if vector.shape!=(384,) or not np.isfinite(vector).all() or not np.isclose(np.linalg.norm(vector),1,atol=1e-5):
        raise ValueError('Invalid new vector')
    updated=np.concatenate([matrix,vector[None,:]])
    assert np.array_equal(updated[:-1],matrix)
    ids=np.asarray(old_ids+[evidence['id']])
    np.save(a.output/'embeddings.npy',updated);np.save(a.output/'embedding_card_ids.npy',ids)
    vector_hash=hashlib.sha256(vector.astype('>f4').tobytes()).hexdigest()
    hashes={cid:r['source_vector_sha256'] for cid,r in vectors.items()};hashes[evidence['id']]=vector_hash
    aggregate=hashlib.md5(''.join(hashes[c] for c in sorted(hashes,key=lambda c:c.encode())).encode()).hexdigest()
    new_manifest=deepcopy(manifest)
    new_manifest.update(indexed_ids=ids.tolist(),indexed_count=len(ids),missing_images=manifest['missing_images']-1,
        embeddings_sha256=digest_file(a.output/'embeddings.npy'),ids_sha256=digest_file(a.output/'embedding_card_ids.npy'),
        parent_embeddings_sha256=manifest['embeddings_sha256'],parent_ids_sha256=manifest['ids_sha256'])
    (a.output/'manifest-before.json').write_text(json.dumps(manifest,indent=2))
    (a.output/'manifest.json').write_text(json.dumps(new_manifest,indent=2))
    np.save(a.output/'new-vector.npy',vector)
    report=dict(card_id=evidence['id'],source=evidence,dimensions=dimensions,
        source_sha256=digest_file(a.source),model_sha256=digest_file(a.model),
        parent_import=parent['import_id'],indexed_before=len(old_ids),indexed_after=len(ids),
        square_aggregate_md5=aggregate,new_vector_sha256=vector_hash,
        parent_vector_bytes_preserved=True,pad_vectors_unchanged=True,
        pad_replay_max_abs_error=float(np.max(np.abs(prior_pad-replay))),
        corrected_card_embeddings_count=len(ids)+parent['metadata']['vectors']['pad']['count'],
        mapping_unchanged=True,published=False,activated=False,
        required_before_activation=['writer access','validated coherent import','frozen regression','staging cutover','activated-import HTML export'])
    (a.output/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))


if __name__=='__main__':main()
