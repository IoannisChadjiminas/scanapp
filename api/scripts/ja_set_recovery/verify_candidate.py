"""Japanese recovery candidate check, adapted from the neo2-057 release verifier.

Run in an isolated API-image container after creating the inactive schema.
Pass the candidate's catalogue and artifact selectors through the environment.

Read-only candidate readiness check; does not open the live results database.
Never prints credentials or raw driver errors.
"""
import json, hashlib, psycopg, certifi, sys
sys.path.insert(0,'/app')
from pathlib import Path
from app.config import Settings
from app.db import init_catalog
from app.planetscale import CloudCatalogConnection, load_cloud_catalogue
from app.recognition.reference_features import ReferenceFeatureStore
from app.recognition.artwork import ArtworkIndex
from app.card_images import display_image_url

settings=Settings().model_copy(update=dict(
    use_grading=False,parallel_grading=False,grading_at_card_deadline=False,
    store_captures=False,scan_lanes=1,
))
import sqlite3
catalog=sqlite3.connect(':memory:',factory=CloudCatalogConnection)
catalog.row_factory=sqlite3.Row
init_catalog(catalog)
snapshot=load_cloud_catalogue(settings,catalog)
rows=[dict(row) for row in catalog.execute('SELECT * FROM cards')]
features=ReferenceFeatureStore.load(settings.reference_features_dir,rows)
artwork=ArtworkIndex.load(settings.artwork_bundle_dir,snapshot=snapshot,
    model_path=settings.dinov2_path,known_ids={row['id'] for row in rows},
    known_languages={row['id']:row['language'] for row in rows})
release=json.loads(Path('/work/release.json').read_text())
new=json.loads(Path('/work/new-ids.json').read_text())
assert snapshot.indexed_count==release['pad_vectors']
assert catalog.execute('SELECT count(*) FROM cards').fetchone()[0]==release['cards_total']
missing=0
for cid in new:
    r=catalog.execute('SELECT * FROM cards WHERE id=?',(cid,)).fetchone()
    assert r is not None
    if r['has_image']:
        assert display_image_url(r,catalog)==f'/api/v1/cards/{cid}/image'
        missing+=not Path(r['image_path']).is_file()
assert missing==0
row=catalog.execute("SELECT * FROM cards WHERE id=?",(new[0],)).fetchone()
# Check the persisted artwork vectors as well as the externally loaded bundle.
try:
    with psycopg.connect(settings.planetscale_database_url.get_secret_value(),
            port=6432,sslmode='verify-full',sslrootcert=certifi.where(),
            connect_timeout=15,prepare_threshold=None) as pg:
        pg.execute('SET TRANSACTION READ ONLY')
        metadata=pg.execute(f'SELECT metadata FROM {settings.planetscale_schema}.import_manifest WHERE import_id=%s',
            (settings.planetscale_import_id,)).fetchone()[0]
        hashes=[]; cards=set(); previous=-1
        with pg.cursor(name='verify_artwork') as cursor:
            cursor.execute(f'SELECT card_id,row_index,source_vector_sha256,public.vector_send(embedding) FROM {settings.planetscale_schema}.artwork_embeddings ORDER BY row_index')
            while batch:=cursor.fetchmany(1000):
                for card_id,index,claimed,binary in batch:
                    raw=bytes(binary)
                    assert index>previous and len(raw)==1540
                    previous=index
                    assert hashlib.sha256(raw[4:]).hexdigest()==claimed
                    hashes.append(claimed);cards.add(card_id)
        assert len(hashes)==metadata['artwork']['count']==release['artwork_regions']
        assert len(cards)==metadata['artwork']['cards']
        assert hashlib.md5(''.join(hashes).encode()).hexdigest()==metadata['artwork']['aggregate_md5']
except Exception as exc:
    raise RuntimeError('Candidate artwork validation failed: '+type(exc).__name__) from None
print(json.dumps(dict(artifacts_ready=True,import_id=settings.planetscale_import_id,
    vectors=snapshot.indexed_count,image_url=display_image_url(row,catalog))))
catalog.close()
