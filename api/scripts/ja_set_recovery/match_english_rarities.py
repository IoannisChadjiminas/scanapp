"""Match English cards without rarity to a source: TCGdex, or the original card they reprint. Offline."""
import json, re, collections, unicodedata
T=''  # folder holding the read-query export of the original sets' cards (see the record)
base=json.load(open('base-cards.json'))
v=list(json.load(open(T+'mcp-plugin_planetscale_planetscale-planetscale_execute_read_query-1795787895960.txt'))['rows'][0].values())[0]
base+=json.loads(v) if isinstance(v,str) else v
idx={}
for i,s,n,name,rar in base:
    m=re.match(r'^0*(\d+)$',str(n)); idx.setdefault((s, m.group(1) if m else str(n)),[]).append((i,name,rar))
rows=json.load(open('missing-en.json')); res=json.load(open('tcgdex-en.json')); pt=json.load(open('ptcg.json'))
CODE={'ASC':['me02.5'],'BLK':['sv10.5b'],'BRS':['swsh9'],'DP':['dp1'],'FL':['ex6'],'GE':['dp4'],'LA':['dp6'],'MD':['dp5'],'MEE':['mee'],'MEG':['me01'],'MT':['dp2'],'PAL':['sv02'],'POR':['me03'],'RS':['ex1'],'SHF':['swsh4.5'],'STF':['dp7'],'SVE':['sve'],'SVI':['sv01'],'SVP':['svp'],'SWSH':['swshp'],
      'cre':['swsh6'],'obf':['sv03'],'paf':['sv04.5'],'pal':['sv02'],'par':['sv04'],'sh01':['swsh1'],'sv1en':['sv01'],'swsh05':['swsh5'],'swsh09':['swsh9'],'swsh10':['swsh10','swsh11'],'swsh12':['swsh12'],'swsh2':['swsh2'],'swsh3':['swsh3','swsh2'],'swsh4':['swsh4'],'swsh7':['swsh7'],'swsh8':['swsh8'],'tem':['sv05'],'twm':['sv06']}
TYPES={'g':'grass','r':'fire','w':'water','l':'lightning','p':'psychic','f':'fighting','d':'darkness','m':'metal'}
def norm(s):
    s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower()
    s=re.sub(r'\[([grwlpfdm])\]',lambda m:TYPES[m.group(1)],s)
    s=re.sub(r'\s*\(.*?\)\s*$','',s); s=re.sub(r'\s+-\s+.*$','',s); s=re.sub(r'\s+lv\.?\s*\d+$','',s)
    s=re.sub(r'^basic\s+','',s); s=s.replace('prof. ','professor ')
    return re.sub(r'[^a-z0-9]+','',s)
# pokemontcg tiers that agree with a TCGdex label (alternates are checked against both)
AGREE={'Common':{'Common'},'Uncommon':{'Uncommon'},'Rare':{'Rare','Rare Holo','Rare Holo GX'},
       'Ultra Rare':{'Rare Ultra','Rare Holo GX'},'Secret Rare':{'Rare Secret','Rare Rainbow'},'Promo':{'Promo'}}
out=[]
for r in rows:
    x=res[r['id']]; pid=r['provider_id'].removeprefix('en:')
    if x['found']:
        ok=x['rarity'] not in (None,'None','')
        out.append({**r,'rarity':x['rarity'] if ok else None,'source':'tcgdex' if ok else 'tcgdex: None','evidence':'https://api.tcgdex.net/v2/en/cards/'+pid}); continue
    m=re.match(r'^(PPS\d|PPP|BKPPR|BKPR)-([A-Z]+)-0*(\d+)$',pid); m2=re.match(r'^tot\d\d-([a-z0-9]+)-0*(\d+)$',pid); m3=re.match(r'^(sm[\d.]+|smp)-(SM)?0*(\d+)[ab]$',pid)
    if m: kind,targets='reprint '+m.group(1),[(s,m.group(3)) for s in CODE.get(m.group(2),[])]
    elif m2: kind,targets='reprint tot',[(s,m2.group(2)) for s in CODE.get(m2.group(1),[])]
    elif m3: kind,targets='alternate',[(m3.group(1),('SM'+m3.group(3)) if m3.group(2) else m3.group(3))]
    else: out.append({**r,'rarity':None,'source':'no source ('+r['set_id']+')'}); continue
    hit=[c for t in targets for c in idx.get(t,[]) if norm(c[1])==norm(r['name'])]
    if len(hit)!=1: out.append({**r,'rarity':None,'source':kind+': original not found','evidence':str(targets)}); continue
    bid,bname,brar=hit[0]
    if not brar or brar=='None': out.append({**r,'rarity':None,'source':kind+': original has none','evidence':bid}); continue
    if kind=='alternate':
        p=(pt.get(r['id']) or {}).get('rarity')
        if p not in AGREE.get(brar,set()):
            out.append({**r,'rarity':None,'source':'alternate: sources disagree','evidence':f'{bid}={brar}, pokemontcg={p}'}); continue
    out.append({**r,'rarity':brar,'source':kind,'evidence':bid})
json.dump(out,open('decisions.json','w'),indent=1,ensure_ascii=False)
c=collections.Counter(o['source'] for o in out)
for k,n in sorted(c.items(),key=lambda x:-x[1]): print(f'{n:4} {k}')
print('filled', sum(1 for o in out if o['rarity']), collections.Counter(o['rarity'] for o in out if o['rarity']))
