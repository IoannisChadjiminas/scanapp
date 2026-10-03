"""Build an additive candidate from the validated ACTIVE cloud snapshot.

Read-only credentials; never publish. Reuse immutable old vectors/features,
append independently reviewed references, and emit a compare-and-swap SQL
transaction for a separately authorized publisher. No legacy SQLite fallback.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import shutil
from pathlib import Path
import sqlite3
import sys
from urllib.parse import urlsplit

import certifi
import cv2
import numpy as np
from PIL import Image
import psycopg

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.db import init_catalog
from app.planetscale import load_cloud_catalogue, _field_token
from app.recognition.artifacts import sha256_file, validate_embeddings
from app.recognition.artwork import PROFILES, crop_profile
from app.recognition.embed import DinoEmbedder
from app.recognition.reference_features import build_reference_bundle, ReferenceFeatureStore, catalogue_signature


def row_digest(rows, columns):
    hashes=[hashlib.md5('|'.join(_field_token(r[c]) for c in columns).encode()).hexdigest()
            for r in sorted(rows,key=lambda r:r['id'].encode())]
    return hashlib.md5(''.join(hashes).encode()).hexdigest()


def literal(value):
    return "'"+value.replace("'","''")+"'"


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selection',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--version',required=True)
    p.add_argument('--features-output',type=Path,required=True,
                   help='New directory pre-populated with regular hardlinks to immutable parent binaries')
    a=p.parse_args()
    cv2.setNumThreads(1)
    settings=Settings(store_captures=False,portfolio_database_url='')
    assert settings.catalogue_backend=='planetscale' and settings.reference_features_dir and settings.artwork_bundle_dir
    output=a.output.resolve(); output.mkdir(exist_ok=False)
    selections=json.loads(a.selection.read_text())['records']
    assert len(selections)==1, 'Current publisher explicitly supports one missing reference per atomic update'
    selection=selections[0]
    assert selection['verification']=='manual_visual' and selection['source_kind']=='independent_catalogue_not_official'
    assert selection['source_page'] and selection['image_url'] and sha256_file(Path(selection['source_file']))==selection['sha256']
    cloud=sqlite3.connect(':memory:'); cloud.row_factory=sqlite3.Row;init_catalog(cloud)
    snapshot=load_cloud_catalogue(settings,cloud)
    rows=[dict(r) for r in cloud.execute('SELECT * FROM cards ORDER BY id')]
    old_row=next(r for r in rows if r['id']==selection['id'])
    assert not old_row['has_image'] and not old_row['image_path'] and selection['id'] not in snapshot.card_ids
    for key in ('name','language','set_id','collector_number','cardmarket_url'):
        assert selection[key]==old_row[key],f'Unverified identity: {key}'
    store=ReferenceFeatureStore.load(settings.reference_features_dir,rows)
    target=sqlite3.connect(output/'catalog.sqlite');target.row_factory=sqlite3.Row;init_catalog(target)
    for table in ('cards','cardmarket_expansion_products'):
        records=[dict(r) for r in cloud.execute(f'SELECT * FROM {table}')]
        columns=list(records[0]); names=','.join(columns)
        target.executemany(f'INSERT INTO {table}({names}) VALUES({",".join("?" for _ in columns)})',
                           [tuple(r[c] for c in columns) for r in records])
    target.execute('INSERT INTO cards_fts(id,name,set_name,collector_number) SELECT id,name,set_name,collector_number FROM cards')
    destination=f'/data/reference-images/recovered/{selection["id"].replace(":","_")}{Path(selection["source_file"]).suffix}'
    target.execute('UPDATE cards SET image_path=?,has_image=1,remote_image_url=? WHERE id=?',
                   (destination,selection['image_url'],selection['id']))
    target.commit(); target.close()
    updated=[dict(r, image_path=destination,has_image=1,remote_image_url=selection['image_url'])
             if r['id']==selection['id'] else r for r in rows]
    model=DinoEmbedder(str(settings.dinov2_path),1,1)
    with Image.open(selection['source_file']) as opened:image=opened.convert('RGB')
    vector=model.embed(image,snapshot.preprocess_config)
    full=output/'vectors';full.mkdir()
    matrix=np.concatenate([snapshot.embeddings,vector[None,:]])
    ids=np.asarray(snapshot.card_ids.tolist()+[selection['id']])
    validate_embeddings(matrix,ids)
    assert np.array_equal(matrix[:-1],snapshot.embeddings)
    np.save(full/'embeddings.npy',matrix);np.save(full/'embedding_card_ids.npy',ids)
    manifest=deepcopy(snapshot.manifest)
    manifest.update(indexed_count=len(ids),indexed_ids=ids.tolist(),missing_images=snapshot.missing_images-1,
        catalogue_version=snapshot.catalogue_version+'-'+a.version,
        embeddings_sha256=sha256_file(full/'embeddings.npy'),ids_sha256=sha256_file(full/'embedding_card_ids.npy'),
        parent_embeddings_sha256=snapshot.embeddings_sha256,parent_ids_sha256=snapshot.ids_sha256,
        recovery_selection_sha256=sha256_file(a.selection))
    (full/'manifest.json').write_text(json.dumps(manifest,indent=2))
    parent=settings.artwork_bundle_dir
    artmanifest=json.loads((parent/'manifest.json').read_text())
    assert artmanifest['base_embeddings_sha256']==snapshot.embeddings_sha256 and artmanifest['base_ids_sha256']==snapshot.ids_sha256
    oldart=np.load(parent/'embeddings.npy',allow_pickle=False)
    records=json.loads((parent/'records.json').read_text())
    assert sha256_file(parent/'embeddings.npy')==artmanifest['embeddings_sha256']
    assert sha256_file(parent/'records.json')==artmanifest['records_sha256']
    assert selection['id'] not in {r['card_id'] for r in records}
    added=[model.embed(crop_profile(image,profile),snapshot.preprocess_config) for profile in PROFILES]
    records.extend(dict(card_id=selection['id'],profile=profile,language=selection['language'],
        name=selection['name'],set_name=old_row['set_name'],collector_number=selection['collector_number'],
        reference_sha256=selection['sha256']) for profile in PROFILES)
    art=output/'artwork';art.mkdir()
    np.save(art/'embeddings.npy',np.concatenate([oldart,np.asarray(added,dtype=np.float32)]))
    (art/'records.json').write_text(json.dumps(records,ensure_ascii=False))
    artmanifest.update(base_embeddings_sha256=manifest['embeddings_sha256'],base_ids_sha256=manifest['ids_sha256'],
        embeddings_sha256=sha256_file(art/'embeddings.npy'),records_sha256=sha256_file(art/'records.json'),
        indexed_regions=len(records),indexed_cards=len({r['card_id'] for r in records}),
        parent_manifest_sha256=sha256_file(parent/'manifest.json'))
    (art/'manifest.json').write_text(json.dumps(artmanifest,indent=2))
    # The caller prepares regular hardlinks on the data filesystem. Never edit
    # an old binary or truncate the shared manifest inode: replace it atomically.
    feat=a.features_output
    assert feat.is_dir() and feat.resolve()!=settings.reference_features_dir.resolve()
    assert json.loads((feat/'manifest.json').read_text())==store.manifest
    featuremanifest=deepcopy(store.manifest)
    source_directory=output/'reference-images'/'recovered';source_directory.mkdir(parents=True)
    copied=source_directory/Path(destination).name
    shutil.copyfile(selection['source_file'],copied)
    one=dict(old_row,image_path=str(copied))
    fragment=build_reference_bundle([one],output,output/'feature-addition')
    record=fragment['records'][selection['id']]
    assert record['available'] and record['source_sha256']==selection['sha256']
    assert not (feat/record['filename']).exists()
    shutil.copyfile(output/'feature-addition'/record['filename'],feat/record['filename'])
    record['image_path']=destination
    featuremanifest['records'][selection['id']]=record
    featuremanifest.update(catalogue_sha256=catalogue_signature(updated),available=featuremanifest['available']+1)
    temporary=feat/'manifest.new.json'
    temporary.write_text(json.dumps(featuremanifest,sort_keys=True,indent=2))
    temporary.replace(feat/'manifest.json')
    ReferenceFeatureStore.load(feat,updated)
    # The read-only role is used to capture immutable audit/CAS inputs only.
    with psycopg.connect(settings.planetscale_database_url.get_secret_value(),port=6432,sslmode='verify-full',
            sslrootcert=certifi.where(),connect_timeout=15,prepare_threshold=None) as pg:
        pg.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        meta,meta_cas=pg.execute(f'SELECT metadata,md5(metadata::text) FROM {settings.planetscale_schema}.import_manifest WHERE import_id=%s',
                        (settings.planetscale_import_id,)).fetchone()
        old_manifest,manifest_cas=pg.execute(f'SELECT metadata,md5(metadata::text) FROM {settings.planetscale_schema}.reference_metadata WHERE source_key=%s',
                                ('vector-manifest:'+snapshot.preprocess_config,)).fetchone()
        hashes=dict(pg.execute(f'SELECT card_id,source_vector_sha256 FROM {settings.planetscale_schema}.card_embeddings WHERE mode=%s',
                               (snapshot.preprocess_config,)).fetchall())
    assert old_manifest==snapshot.manifest
    newmeta=deepcopy(meta)
    newmeta['digests']['cards']['md5']=row_digest(updated,newmeta['digests']['cards']['columns'])
    newhash=hashlib.sha256(np.asarray(vector,dtype='>f4').tobytes()).hexdigest(); hashes[selection['id']]=newhash
    stats=newmeta['vectors'][snapshot.preprocess_config]
    stats.update(count=len(hashes),aggregate_md5=hashlib.md5(''.join(hashes[c] for c in sorted(hashes,key=lambda c:c.encode())).encode()).hexdigest())
    newmeta['reference_recovery']=dict(version=a.version,card_id=selection['id'],reference=selection,
        existing_vectors_preserved=True,mappings_unchanged=True,parent_cards_md5=meta['digests']['cards']['md5'])
    (output/'before.json').write_text(json.dumps(dict(metadata=meta,manifest=old_manifest,card=old_row),indent=2))
    schema=settings.planetscale_schema
    vector_literal=literal('['+','.join(str(float(v)) for v in vector)+']')+'::public.vector'
    # All four mutations are in ONE statement. An unexpected missing CAS step
    # raises division-by-zero, rolling back everything instead of partial state.
    sql=f'''WITH gate AS (SELECT import_id FROM {schema}.import_manifest
      WHERE import_id={literal(settings.planetscale_import_id)} AND status='validated'
        AND md5(metadata::text)={literal(meta_cas)} FOR UPDATE),
    card AS (UPDATE {schema}.cards SET image_path={literal(destination)},has_image=1,
      remote_image_url={literal(selection['image_url'])} FROM gate
      WHERE id={literal(selection['id'])} AND has_image=0 AND (image_path IS NULL OR image_path='') RETURNING id),
    vector AS (INSERT INTO {schema}.card_embeddings(card_id,mode,snapshot_id,embedding,source_vector_sha256)
      SELECT id,{literal(snapshot.preprocess_config)},{literal(stats['snapshot'])},{vector_literal},{literal(newhash)} FROM card RETURNING card_id),
    reference AS (UPDATE {schema}.reference_metadata SET metadata={literal(json.dumps(manifest))}::jsonb FROM vector
      WHERE source_key={literal('vector-manifest:'+snapshot.preprocess_config)} AND md5(metadata::text)={literal(manifest_cas)} RETURNING source_key),
    audit AS (UPDATE {schema}.import_manifest SET metadata={literal(json.dumps(newmeta))}::jsonb,
      validated_at=now() FROM reference WHERE import_id={literal(settings.planetscale_import_id)} RETURNING import_id)
    SELECT 1/(CASE WHEN (SELECT count(*) FROM audit)=1 THEN 1 ELSE 0 END) AS atomic_recovery_applied;'''
    (output/'publish.sql').write_text(sql)
    (output/'report.json').write_text(json.dumps(dict(version=a.version,card_id=selection['id'],
        existing_vectors_unchanged=True,mappings_unchanged=True,indexed=len(ids),
        full_vector_sha256=newhash,source_sha256=selection['sha256'],catalogue_signature=featuremanifest['catalogue_sha256'],
        sql_sha256=hashlib.sha256(sql.encode()).hexdigest(),published=False),indent=2))
    print(json.dumps(dict(phase='candidate_validated_not_published',indexed=len(ids),card_id=selection['id'])),flush=True)

if __name__=='__main__':main()
