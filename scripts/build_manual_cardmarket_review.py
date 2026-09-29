"""Build the saved manual review; no model inference and no database writes.

Decisions refer to inspected contact sheets, not automatically inferred matches.
Run from the repository root after preparing exports/matching-audit/manual.
"""
import base64
import collections
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path('exports/matching-audit')
OUT = ROOT / 'manual'


def read(path):
    return json.loads(path.read_text())


def main():
    snapshot = read(OUT / 'current-snapshot.json')
    checked_path = OUT / 'image-checked-applied.json'
    applied_checked = {r['url']: r for r in read(checked_path)} if checked_path.exists() else {}
    cards = {c['id']: c for c in snapshot['cards']}
    products = snapshot['cardmarket_expansion_products']
    old = {r['url']: r for r in read(ROOT / 'review.json')['rows']}
    proposals = {r['url']: r for r in read(ROOT / 'combined-proposed-matches.json')}
    linked = {r['product']['url']: i + 1 for i, r in enumerate(read(OUT / 'linked-sheet-index.json'))}
    wrong = {r['product']['url']: i + 1 for i, r in enumerate(read(OUT / 'wrong-sheet-index.json'))}
    sheet = read(OUT / 'sheet-index.json')
    inspected = {v['url']: k for k, v in sheet.items()}
    # Explicit identity choices from the manually inspected 30th sheets.
    classic = {1:27, 2:13, 3:1, 4:11, 5:6, 8:2, 9:15, 10:4,
               11:18, 12:9, 13:29, 14:23, 15:30, 16:3, 20:26,
               21:5, 22:21, 23:22, 24:8, 25:14, 26:12, 27:16,
               28:25, 29:24, 30:7, 31:17, 32:10, 33:28}
    classic = {sheet[f'30th-{n}']['url']: f'en:30th-c-{c:03d}' for n, c in classic.items()}
    metal = sheet['anniversary-6']['url']
    photos = read(ROOT / 'embedded-photos.json') | read(OUT / 'matched-embedded.json')
    rows = []
    for p in products:
        if not p.get('listing_image_url'):
            continue
        url = p['url']; prior = old.get(url, {})
        row = dict(url=url, name=p['name'].split('From')[0].strip(), expansion=p['expansion'],
                   existing_card_id=p.get('card_id'), database_linked=bool(p['matched']),
                   listing_image_url=p['listing_image_url'], photo_available=url in photos,
                   candidates=[], inspected=False, evidence=None,
                   status='unresolved', note=prior.get('reason', 'No independently verified print candidate.'))
        if url in linked:
            n = linked[url]
            row.update(status='existing_checked', candidates=[p['card_id']], inspected=True,
                       evidence=f'linked-{(n-1)//20+1}.jpg, pair {n}',
                       note='Listing and official image manually compared: artwork, language, layout and visible print features agree. Metadata supplies the collector identity. Fine finish/edition differences below thumbnail resolution are not verified.')
        elif url in wrong:
            n = wrong[url]
            row.update(status='wrong_link', candidates=[p['card_id']], inspected=True,
                       evidence=f'wrong-{(n-1)//20+1}.jpg, pair {n}',
                       note='Incorrect exact-print link: Japanese listing, English catalogue card. Manually compared artwork agrees, so this is a shared-art relationship only. Correct Japanese print is absent from this snapshot; do not retain this as an exact Cardmarket link.')
        elif p['matched']:
            row.update(status='existing_no_art', candidates=[p['card_id']],
                       note='Existing database link. The catalogue has no official image for a two-sided visual check; exact-print verification remains pending.')
        elif url in proposals:
            q = proposals[url]
            status = 'proposed_visual' if q.get('visual_review') else 'proposed_metadata'
            if q.get('required_catalogue_correction'):
                status = 'proposed_correction'
                row['required_catalogue_correction'] = q['required_catalogue_correction']
            row.update(status=status, candidates=[q['proposed_card_id']], inspected=bool(q.get('visual_review')),
                       note=q.get('visual_review') or q['reason'],
                       evidence='Saved manual comparison; contact sheets 1–8 for the initial 94. N and M Tyranitar images re-inspected in this manual pass.' if q.get('visual_review') else 'Metadata only; official image missing.')
        elif url not in photos:
            row.update(status='photo_unavailable', note='Stored image URL exists, but no cached photo was recovered and the source returned HTTP 403. No visual match can be verified from this image.')
        elif prior.get('status') == 'non_catalogue_item':
            row.update(status='non_card', note=prior['reason'])
        elif prior.get('status') in ('metadata_conflict', 'separate_variant'):
            row.update(status='hold', note=prior['reason'])

        if url in inspected:
            key = inspected[url]; row['inspected'] = True
            group, n = key.rsplit('-', 1)
            row['evidence'] = f'{group}-{(int(n)-1)//20+1}.jpg, listing {n}'
            if group == 'battle2020':
                row.update(status='missing_print', note='Manually inspected English Battle Academy 2020 photo. Deck-specific stamp/position distinguishes this from the ordinary set print. These deck records are absent from the current catalogue; same artwork cannot establish an exact link.')
            elif group == 'anniversary' and int(n) != 6:
                row.update(status='missing_print', note='Manually inspected Japanese 25th-anniversary print and logo. Its s8a-P/s8a-G print, or this specific unnumbered s8a energy, is absent from the catalogue snapshot. Ordinary or English versions are different prints.')
            elif group == 'promos':
                if int(n) in (1,4,5,6,7,8):
                    row.update(status='hold', note='Listing explicitly says “Oversized Card / Not Tournament Legal.” Do not attach this product to the ordinary-sized catalogue print.')
                elif int(n) == 2:
                    row.update(status='hold', candidates=['en:bwp-BW100'], note='N V1 lacks the Pokémon League stamp visible in the catalogue image. V2 is the corresponding stamped listing; V1 remains a separate variant.')
                elif int(n) >= 9:
                    row.update(status='missing_print', note='Japanese movie/ADV promo photo manually inspected. The corresponding Japanese promo set is absent from this catalogue snapshot. English counterparts or other Japanese printings cannot substitute for this print.')
            elif group == '30th':
                if url in classic:
                    row.update(status='provisional', candidates=[classic[url]], database_linked=True,
                               fixed='Linked to the 30th Classic Collection card. The anniversary scan is stored on the server and indexed. The printed number is saved alongside the catalogue number.',
                               note='English anniversary-stamped card linked to its 30th Classic Collection record. The anniversary scan is stored on the server and indexed. The listing keeps the original printed number, and that number is saved on the 30th card as well.')
                elif int(n) == 6:
                    row.update(status='ambiguous', candidates=['en:30th-c-019','en:30th-c-020'],
                               fixed='Listing 1 (30C TM 100) opens en:30th-c-020. Listing 2 (30C TM 99) opens en:30th-c-019. Both images are stored on the server and indexed.',
                               note='Bottom half, 30C TM 100. The photo shows Lost Crisis and Moon\'s Invite. Linked to en:30th-c-020. The image is stored on the server and indexed.',
                               candidate_notes={'en:30th-c-019':'Top half, printed 99/102. Linked to 30C TM 99.','en:30th-c-020':'Bottom half, printed 100/102. Linked to this listing, 30C TM 100.'})
                elif int(n) == 7:
                    row.update(status='ambiguous', candidates=['en:30th-c-019','en:30th-c-020'],
                               fixed='Listing 1 (30C TM 100) opens en:30th-c-020. Listing 2 (30C TM 99) opens en:30th-c-019. Both images are stored on the server and indexed.',
                               note='Top half, 30C TM 99. The photo shows the artwork, HP 150 and the legend rule, with no attacks. Linked to en:30th-c-019. The image is stored on the server and indexed.',
                               candidate_notes={'en:30th-c-019':'Top half, printed 99/102. Linked to this listing, 30C TM 99.','en:30th-c-020':'Bottom half, printed 100/102. Linked to 30C TM 100.'})
                else:
                    row.update(status='missing_print', note='Anniversary Mew colour variant visually inspected. No corresponding record exists in the 30th Classic Collection catalogue set.')
        if url == metal:
            row.update(status='proposed_visual', candidates=['ja:S8a-MET'], inspected=True,
                       note='New manual match: Japanese Metal Energy. Listing and official image agree in energy symbol, silver-blue background, Japanese text, 25th logo and s8a MET marking. Catalogue name “Unknown” prevented name matching; correct display name to Metal Energy.',
                       evidence='anniversary-1.jpg listing 6; official/ja_S8a-MET.webp inspected at full size.')
        checked = applied_checked.get(url)
        if checked:
            row.update(status='saved_indexed', candidates=[checked['card_id']], database_linked=True,
                       inspected=True, note=checked['note'])
        rows.append(row)

    photo_rows = list(rows)
    medium_path = OUT / 'medium-fix.json'
    medium = read(medium_path) if medium_path.exists() else {'counts': {}, 'rows': []}
    rows.extend(medium['rows'])
    order = ['saved_indexed','saved_unindexed','linked_kept_url','linked_version','url_number_exception','url_number_exception_kept','pending_url_check','skipped_mismatch','skipped_oversized','medium_fix','medium_variant','wrong_link','proposed_visual','proposed_correction','proposed_metadata','provisional','ambiguous','hold','existing_checked','existing_no_art','missing_print','unresolved','photo_unavailable','non_card']
    rows.sort(key=lambda r:(order.index(r['status']),r['expansion'],r['name']))
    counts = collections.Counter(r['status'] for r in rows)
    stats = dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 catalogue_cards=len(cards), products=len(products),
                 unlinked_products=sum(not p['matched'] for p in products),
                 unlinked_with_photo=sum(not r['database_linked'] for r in photo_rows),
                 products_with_photo=len(photo_rows), cached_photos=len(photos),
                 photos_manually_inspected=sum(r['inspected'] for r in photo_rows),
                 catalogue_without_image=sum(not c['has_image'] for c in cards.values()),
                 medium=medium['counts'], statuses=dict(counts))
    (OUT/'decisions.json').write_text(json.dumps({'summary':stats,'rows':rows},ensure_ascii=False,indent=2))
    (OUT/'proposed-matches.json').write_text(json.dumps([r for r in rows if r['status'].startswith('proposed_')],ensure_ascii=False,indent=2))
    # Embed available images so the delivered HTML can be opened independently.
    images = {}; display_cards = {}
    for r in rows:
        if r['url'] in photos:
            key = 'p'+hashlib.sha256(r['url'].encode()).hexdigest()[:20]
            images[key] = photos[r['url']]; r['photo_key'] = key
        for cid in r['candidates']:
            if cid in display_cards: continue
            c = cards[cid]
            display_cards[cid] = {k:c.get(k) for k in ('id','name','language','collector_number','set_name','remote_image_url')}
            files = list((OUT/'official').glob(cid.replace(':','_')+'.*'))
            if files:
                f = files[0]; key = 'c'+cid
                mime = 'image/jpeg' if f.suffix in ('.jpg','.jpeg') else 'image/webp'
                images[key] = 'data:'+mime+';base64,'+base64.b64encode(f.read_bytes()).decode()
                display_cards[cid]['photo_key'] = key
    payload = json.dumps({'summary':stats,'rows':rows,'cards':display_cards,'images':images},ensure_ascii=False).replace('</','<\\/')
    template = Path('scripts/manual_cardmarket_review.html').read_text()
    (OUT/'standalone.html').write_text(template.replace('__REVIEW_DATA__',payload))
    # The browser preview uses cached assets to avoid a 100 MB page transfer.
    for r in rows:
        if r.get('photo_key'):
            filename = hashlib.sha256(r['listing_image_url'].encode()).hexdigest()[:20]+'.img'
            images[r['photo_key']] = '../photos/'+filename
    for cid, c in display_cards.items():
        if c.get('photo_key'):
            files = list((OUT/'official').glob(cid.replace(':','_')+'.*'))
            images[c['photo_key']] = 'official/'+files[0].name
    payload = json.dumps({'summary':stats,'rows':rows,'cards':display_cards,'images':images},ensure_ascii=False).replace('</','<\\/')
    (OUT/'final.html').write_text(template.replace('__REVIEW_DATA__',payload))
    print(json.dumps(stats,indent=2))
    print('HTML bytes:',(OUT/'final.html').stat().st_size)


if __name__ == '__main__':
    main()
