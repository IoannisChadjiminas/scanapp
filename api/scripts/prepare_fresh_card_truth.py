"""Bind reviewed photo identities, retaining the disclosed post-baseline truth audit."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3

ROOT=Path(__file__).resolve().parents[2]

def normalize(value):return re.sub(r'[^a-z0-9]','',value.lower())

def main():
    path=ROOT/'docs/grading-fresh100-frozen-sources-20261002.json'
    sources=json.loads(path.read_text())
    catalogue=ROOT/'data/image-recovery/20261002-official/verified-final-v5/catalog.sqlite'
    conn=sqlite3.connect('file:'+str(catalogue)+'?mode=ro',uri=True);conn.row_factory=sqlite3.Row
    overrides={
        ('Gengar & Mimikyu GX','038/095','ja'):['ja:SM9-038'],
        ('Dragonite','065/095','ja'):['ja:SM9-065'],
        ('Lucario & Melmetal GX','083/173','ja'):['ja:SM12a-083'],
        ('Pikachu & Zekrom GX','041/173','ja'):['ja:SM12a-041'],
        ('Timburr','109/101','ja'):['ja:SV6-109'],
        ('Professor Oak','026/032','ja'):['ja:CLF-026'],
        ('Magneton','9/102','en'):['en:base1-9'],
        ('Venusaur','15/102','en'):['en:base1-15'],
        ('Gyarados','6/102','en'):['en:base1-6'],
        ('Gyarados','007/034','en'):['en:CLB-007'],
        ('Pikachu','051/162','en'):['en:sv05-051'],
        ('Pikachu','15/17','en'):['en:pop9-15'],
        ('Shaymin V','013/172','en'):['en:swsh9-013'],
        ('Eevee ex','075/131','en'):['en:sv08.5-075'],
        # The photographed TAG holder explicitly says SILVER TEMPEST.
        # The original binding error was found after the baseline, not before it.
        ('Gardevoir','TG05/TG30','en'):['en:swsh12tg-TG05'],
        ('Mega Charizard X ex','MOP023','en'):['en:mep-023'],
    }
    records=[]
    for photo in sources['photos']:
        t=photo['manual_truth'];key=(t['name'],t['number'],t['language'])
        ids=overrides.get(key)
        if ids is None:
            number=t['number'].split('/')[0]
            if number.startswith('SVP'):number=number[3:]
            found=conn.execute('SELECT id,name,collector_number,set_id FROM cards WHERE language=?',(t['language'],)).fetchall()
            found=[r for r in found if normalize(r['name'])==normalize(t['name'])
                   and normalize(r['collector_number']).lstrip('0')==normalize(number).lstrip('0')]
            # English provider aliases represent the same catalogue printing.
            canonical={r['id'] if r['id'].startswith(t['language']+':') else t['language']+':'+r['id'] for r in found}
            ids=sorted(canonical) if len(canonical)==1 else []
        assert all(conn.execute('SELECT 1 FROM cards WHERE id=?',(pid,)).fetchone() for pid in ids)
        records.append({'id':photo['id'],'expected_card_ids':ids,
                        'truth_scope':'set/collector/language; finish, stamp and authenticity unscored',
                        'unscored_reason':None if ids else 'No independently resolved catalogue printing; retained, not removed'})
    report={'sources_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'catalogue_sha256':hashlib.sha256(catalogue.read_bytes()).hexdigest(),
        'annotations':'Card IDs initially bound before card-matching inference from visible identities and read-only catalogue; the Gardevoir set binding was audited after baseline inference. Japanese translations checked against catalogue names.',
        'annotation_corrections':[{'id':'fresh100_206285662050','original_number':'MOP023','correct_number':'MEP023',
            'reason':'Full-resolution original-pixel re-review before card inference. Grader/grade truth remains unchanged.'},
            {'id':'freshextra_5_636235657','original_card_id':'en:swsh10tg-TG05',
             'correct_card_id':'en:swsh12tg-TG05','audit_timing':'after baseline inference',
             'reason':'Printed holder set SILVER TEMPEST; original and audited truth files remain preserved.'}],
        'photos':records}
    with (ROOT/'docs/grading-fresh100-card-truth-20261002.json').open('x') as handle:json.dump(report,handle,indent=2)
    print(json.dumps({'scorable':sum(bool(p['expected_card_ids']) for p in records),'unscored':[p for p in records if not p['expected_card_ids']]}))

if __name__=='__main__':main()
