"""Prepare a reviewed source cohort in a disposable snapshot; no external writes."""
import argparse
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import shutil
import sqlite3
import sys

import cv2
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.artifacts import sha256_file, validate_embeddings
from app.recognition.artwork import PROFILES, crop_profile
from app.recognition.embed import DinoEmbedder
from app.recognition.reference_features import build_reference_bundle, catalogue_signature
from assemble_reference_feature_release import assemble
from prepare_offline_reference_pilot import validate_selection


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for field in ('parent','parent-features','selection','model','output'):
        p.add_argument('--'+field,type=Path,required=True)
    a=p.parse_args();cv2.setNumThreads(1)
    selected=json.loads(a.selection.read_text())['records']
    if not selected or len(selected)>50 or len({r['id'] for r in selected})!=len(selected):
        raise ValueError('Pilot must contain 1–50 unique reviewed references')
    selected=sorted(selected,key=lambda r:r['id'])
    old=sqlite3.connect((a.parent/'catalog.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    old.row_factory=sqlite3.Row;rows=[dict(r) for r in old.execute('SELECT * FROM cards')]
    by_id={r['id']:r for r in rows}
    manifest=json.loads((a.parent/'vectors/manifest.json').read_text())
    if sha256_file(a.model)!=manifest['dinov2_sha256']:raise ValueError('Pinned model mismatch')
    for s in selected:
        validate_selection(by_id[s['id']],s)
        if sha256_file(Path(s['source_file']))!=s['sha256']:raise ValueError('Source checksum mismatch')
    old_matrix=np.load(a.parent/'vectors/embeddings.npy',allow_pickle=False)
    old_ids=np.load(a.parent/'vectors/embedding_card_ids.npy',allow_pickle=False)
    if (sha256_file(a.parent/'vectors/embeddings.npy')!=manifest['embeddings_sha256'] or
        sha256_file(a.parent/'vectors/embedding_card_ids.npy')!=manifest['ids_sha256'] or
        any(s['id'] in old_ids for s in selected)):raise ValueError('Parent vector drift or duplicate')
    art_manifest=json.loads((a.parent/'artwork/manifest.json').read_text())
    for filename,key in [('embeddings.npy','embeddings_sha256'),('records.json','records_sha256')]:
        if sha256_file(a.parent/'artwork'/filename)!=art_manifest[key]:raise ValueError('Artwork drift')
    old_art=np.load(a.parent/'artwork/embeddings.npy',allow_pickle=False)
    art_records=json.loads((a.parent/'artwork/records.json').read_text())
    if any(r['card_id'] in {s['id'] for s in selected} for r in art_records):raise ValueError('Existing artwork would be duplicated')
    a.output.mkdir(parents=True,exist_ok=False)
    target=sqlite3.connect(a.output/'catalog.sqlite');old.backup(target);old.close()
    source_dir=a.output/'reference-images/recovered';source_dir.mkdir(parents=True)
    model=DinoEmbedder(str(a.model),1,1)
    pad=[];square=[];art=[];feature_rows=[];ledger=[]
    for number,s in enumerate(selected,1):
        source=Path(s['source_file']);card=by_id[s['id']]
        destination='/data/reference-images/recovered/'+s['id'].replace(':','_')+source.suffix
        target.execute('UPDATE cards SET image_path=?,has_image=1,remote_image_url=? WHERE id=?',
                       (destination,s['image_url'],s['id']))
        ledger.append(dict(card_id=s['id'],before={k:card[k] for k in ['image_path','has_image','remote_image_url']},after=dict(image_path=destination,has_image=1,remote_image_url=s['image_url']),source_sha256=s['sha256'],mapping_unchanged=True))
        card.update(image_path=destination,has_image=1,remote_image_url=s['image_url'])
        copied=source_dir/(s['id'].replace(':','_')+source.suffix);shutil.copyfile(source,copied)
        feature_rows.append(dict(card,image_path=str(copied)))
        if sha256_file(copied)!=s['sha256']:raise ValueError('Copied source checksum mismatch')
        with Image.open(copied) as original:image=original.convert('RGB')
        pad.append(model.embed(image,'pad'));square.append(model.embed(image,'square'))
        for profile in PROFILES:
            art.append(model.embed(crop_profile(image,profile),'pad'))
            art_records.append(dict(card_id=s['id'],profile=profile,language=card['language'],name=card['name'],set_name=card['set_name'],collector_number=card['collector_number'],reference_sha256=s['sha256']))
        print(json.dumps(dict(phase='reference_vectors',number=number,total=len(selected),card_id=s['id'])),flush=True)
    target.commit();target.close()
    full=a.output/'vectors';full.mkdir();ids=np.asarray(old_ids.tolist()+[s['id'] for s in selected])
    matrix=np.concatenate([old_matrix,np.asarray(pad,dtype=np.float32)]);validate_embeddings(matrix,ids)
    assert np.array_equal(matrix[:-len(selected)],old_matrix)
    np.save(full/'embeddings.npy',matrix);np.save(full/'embedding_card_ids.npy',ids)
    sq=np.asarray(square,dtype=np.float32);validate_embeddings(sq,np.asarray([s['id'] for s in selected]))
    np.save(a.output/'new-square-vectors.npy',sq);np.save(a.output/'new-source-card-ids.npy',np.asarray([s['id'] for s in selected]))
    manifest.update(parent_embeddings_sha256=sha256_file(a.parent/'vectors/embeddings.npy'),parent_ids_sha256=sha256_file(a.parent/'vectors/embedding_card_ids.npy'),indexed_count=len(ids),indexed_ids=ids.tolist(),missing_images=manifest['missing_images']-len(selected),catalogue_version=manifest['catalogue_version']+'-english-source-pilot',embeddings_sha256=sha256_file(full/'embeddings.npy'),ids_sha256=sha256_file(full/'embedding_card_ids.npy'))
    (full/'manifest.json').write_text(json.dumps(manifest,indent=2))
    artwork=a.output/'artwork';artwork.mkdir();art_matrix=np.concatenate([old_art,np.asarray(art,dtype=np.float32)])
    assert np.array_equal(art_matrix[:-len(art)],old_art)
    np.save(artwork/'embeddings.npy',art_matrix);(artwork/'records.json').write_text(json.dumps(art_records,ensure_ascii=False))
    art_manifest.update(base_embeddings_sha256=manifest['embeddings_sha256'],base_ids_sha256=manifest['ids_sha256'],indexed_regions=len(art_records),indexed_cards=len({r['card_id'] for r in art_records}),embeddings_sha256=sha256_file(artwork/'embeddings.npy'),records_sha256=sha256_file(artwork/'records.json'))
    (artwork/'manifest.json').write_text(json.dumps(art_manifest,indent=2))
    delta=build_reference_bundle(feature_rows,a.output,a.output/'feature-delta')
    for s in selected:
        record=delta['records'][s['id']]
        if not record['available'] or record['source_sha256']!=s['sha256']:raise ValueError('Feature source mismatch')
        record['image_path']=by_id[s['id']]['image_path']
    delta['catalogue_sha256']=catalogue_signature([by_id[s['id']] for s in selected])
    (a.output/'feature-delta/manifest.json').write_text(json.dumps(delta,sort_keys=True,indent=2))
    parent_features=json.loads((a.parent_features/'manifest.json').read_text())
    expected={k:r.get('source_sha256') if r['available'] else None for k,r in parent_features['records'].items()}
    expected.update({s['id']:s['sha256'] for s in selected})
    parent_rows=[dict(r) for r in rows]
    # Restore old image bindings for parent validation from the immutable ledger.
    for correction in ledger:
        next(r for r in parent_rows if r['id']==correction['card_id']).update(correction['before'])
    vector_hashes=[dict(card_id=s['id'],pad_sha256=hashlib.sha256(np.asarray(pad[i],dtype='>f4').tobytes()).hexdigest(),square_sha256=hashlib.sha256(np.asarray(square[i],dtype='>f4').tobytes()).hexdigest(),source_sha256=s['sha256']) for i,s in enumerate(selected)]
    (a.output/'new-vector-hashes.json').write_text(json.dumps(vector_hashes,indent=2))
    report=assemble(a.parent_features,parent_rows,rows,a.output/'features',expected,a.output/'feature-delta')
    report.update(references=len(selected),old_pad_rows=len(old_ids),old_artwork_rows=len(old_art),pad_additions=len(pad),square_additions=len(square),artwork_additions=len(art),existing_vector_bytes_preserved=True,mappings_unchanged=True,full_regression_passed=False,publication_approved=False,published=False,activated=False)
    (a.output/'correction-ledger.json').write_text(json.dumps(ledger,indent=2));(a.output/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)


if __name__=='__main__':main()
