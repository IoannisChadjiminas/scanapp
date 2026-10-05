"""Transport an already reviewed overlay through bounded MCP SQL payloads."""
import argparse,hashlib,json
from pathlib import Path
from collections import defaultdict
from prepare_catalogue_overlay_plan import update_sql,insert_sql,value_sql,guard
from prepare_catalogue_seed_plan import literal

SCHEMA='pokesingle_completion_20261004'
PARENT='pokesingle_recovery_20261003'
IMPORT='PS-CATALOGUE-EN-001-20261004'
MAX_BYTES=60000

def snapshot_sql(changes):
    modes={x['before']['mode'] for x in changes};snapshots={x['after']['snapshot_id'] for x in changes}
    old={x['before']['snapshot_id'] for x in changes}
    if len(modes)!=1 or len(snapshots)!=1 or len(old)!=1:raise ValueError('Mixed snapshot scope')
    for x in changes:
        if set(x['before'])!={'card_id','mode','snapshot_id','source_vector_sha256'} or dict(x['before'],snapshot_id=x['after']['snapshot_id'])!=x['after']:raise ValueError('Unexpected snapshot mutation')
    ids=[x['before']['card_id'] for x in changes]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate snapshot key')
    # Explicit immutable-parent CAS checks every stored hash, old snapshot and
    # actual embedding; exact selected keys are retained in the original ledger.
    keys=','.join(literal(x) for x in ids)
    return ('WITH changed AS (UPDATE '+SCHEMA+'.card_embeddings t SET snapshot_id='+literal(next(iter(snapshots)))+
        ' FROM '+PARENT+'.card_embeddings p WHERE t.card_id=p.card_id AND t.mode=p.mode AND t.mode='+literal(next(iter(modes)))+
        ' AND t.snapshot_id=p.snapshot_id AND p.snapshot_id='+literal(next(iter(old)))+
        ' AND t.source_vector_sha256=p.source_vector_sha256 AND t.embedding=p.embedding AND t.card_id IN ('+keys+') AND '+guard(SCHEMA,IMPORT)+
        ' RETURNING 1) SELECT count(*) AS rows_changed FROM changed;')

def manifest_sql(change):
    before,after=change['before'],change['after'];key=before['source_key']
    if key!=after['source_key'] or key not in ('vector-manifest:pad','vector-manifest:square'):raise ValueError('Manifest identity drift')
    bm,am=before['metadata'],after['metadata']
    if set(bm)!=set(am) or len(set(am['indexed_ids']))!=len(am['indexed_ids']):raise ValueError('Manifest key drift')
    if not set(bm['indexed_ids'])<=set(am['indexed_ids']):raise ValueError('Parent vector loss')
    if am['indexed_ids'][:len(bm['indexed_ids'])]!=bm['indexed_ids']:raise ValueError('Manifest order drift')
    additions=am['indexed_ids'][len(bm['indexed_ids']):]
    patch={k:v for k,v in am.items() if k!='indexed_ids' and v!=bm[k]};mode=key.split(':')[1]
    return ('WITH changed AS (UPDATE '+SCHEMA+'.reference_metadata t SET metadata=jsonb_set(t.metadata || '+value_sql(patch,'jsonb')+
        ",'{indexed_ids}',(t.metadata->'indexed_ids') || "+value_sql(additions,'jsonb')+') FROM '+PARENT+
        '.reference_metadata p WHERE t.source_key='+literal(key)+' AND p.source_key=t.source_key AND t.metadata=p.metadata AND '+guard(SCHEMA,IMPORT)+
        ' RETURNING 1) SELECT count(*) AS rows_changed FROM changed;')

def types_for(table,row):
    return {k:('vector' if k=='embedding' else 'jsonb' if k=='metadata' else 'bigint' if k=='cardmarket_id' else 'integer' if k in ('has_image','cardmarket_verified','row_index') else 'text') for k in row}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    original=[json.loads(x) for x in a.input.read_text().splitlines()];result=[]
    def add(b,rows,sql):
        if len(sql.encode())>MAX_BYTES:raise ValueError('Oversized MCP payload')
        result.append(dict(batch_id=f'mcp-overlay-{len(result)+1:03}',original_batch=b['batch_id'],table=b['table'],operation=b['operation'],expected_rows=len(rows),sql=sql,sql_sha256=hashlib.sha256(sql.encode()).hexdigest()))
    for b in original:
        if hashlib.sha256(b['sql'].encode()).hexdigest()!=b['sql_sha256']:raise ValueError('Reviewed SQL drift')
        rows=b['ledger'];table=b['table'];op=b['operation']
        if table=='card_embeddings' and op=='update':
            groups=defaultdict(list)
            for x in rows:groups[x['before']['mode']].append(x)
            for group in groups.values():add(b,group,snapshot_sql(group))
        elif table=='reference_metadata' and op=='update':add(b,rows,manifest_sql(rows[0]))
        else:
            sample=rows[0]['before'] if op=='update' else rows[0];types=types_for(table,sample)
            keys=['id'] if table=='cards' else []
            offset=0
            while offset<len(rows):
                size=min(50,len(rows)-offset)
                while True:
                    group=rows[offset:offset+size]
                    sql=(update_sql(SCHEMA,IMPORT,table,group,keys,types) if op=='update' else insert_sql(SCHEMA,IMPORT,table,group,types))
                    if len(sql.encode())<=MAX_BYTES:break
                    if size==1:raise ValueError('Individual payload too large')
                    size=max(1,size//2)
                add(b,group,sql);offset+=size
    a.output.mkdir(exist_ok=False)
    for r in result:(a.output/(r['batch_id']+'.sql')).write_text(r.pop('sql'))
    (a.output/'index.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(dict(statements=len(result),reviewed_statements=len(original),max_payload_bytes=MAX_BYTES,executed=False)))
if __name__=='__main__':main()
