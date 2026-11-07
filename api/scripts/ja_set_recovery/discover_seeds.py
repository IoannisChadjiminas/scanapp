#!/usr/bin/env python3
"""Match the frozen recovery registry against an observed Cardmarket master index.

Exact titles and reviewed title aliases are collection routes, not card-level
identity proof. Shared/combined listings and fuzzy matches remain review cases.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from local_client import RUN
from collect_listings import write_json

# Explicit title translations. Values must exist in the observed index; no slug is inferred.
ALIASES = {
 'ja-ref-34': 'MEGA Starter Set Sprigatito & Meowscarada ex',
 'ja-ref-618': 'BREAK Starter Pack',
 'ja-ref-144': 'Scarlet & Violet Battle Academy',
 'ja-ref-73': 'M-P Promos',
 'ja-ref-165': 'Pokémon Card Game Classic: Blastoise & Suicune ex Deck',
 'ja-ref-168': 'Pokémon Card Game Classic: Charizard & Ho-Oh ex Deck',
 'ja-ref-171': 'Pokémon Card Game Classic: Venusaur & Lugia ex Deck',
 'ja-ref-388': 'Explosive Flame Walker',
 'ja-ref-569': 'Strength Expansion Pack Sun & Moon',
 'ja-ref-784': 'BW Promos',
 'ja-ref-1018': 'Pokémon Card web',
 'ja-ref-1020': 'Pokémon Card VS',
 'ja-ref-243': 'Special Battle Set Charizard VSTAR vs Rayquaza VMAX',
 'ja-ref-282': 'Sword & Shield Starter Set Darkrai VSTAR',
 'ja-ref-361': 'VMAX Starter Deck: Blastoise VMAX',
 'ja-ref-367': 'VMAX Starter Deck: Venusaur VMAX',
 'ja-ref-355': 'Single Strike & Rapid Strike Premium Trainer Boxes',
 'ja-ref-346': 'Silver Lance & Jet Black Spirit Jumbo Pack Set',
 'ja-ref-486': 'Eevee GX Starter Sets',
 'ja-ref-554': 'Ash vs Team Rocket Deck Kit',
 'ja-ref-575': 'Sun & Moon Starter Set',
 'ja-ref-592': 'The Best of XY',
 'ja-ref-606': 'Premium Champion Pack',
 'ja-ref-612': 'MAudino EX Mega Battle Deck',
 'ja-ref-615': 'Zygarde EX Perfect Battle Deck',
 'ja-ref-647': 'Emboar EX vs Togekiss EX Deck Kit',
 'ja-ref-659': 'MRayquaza EX Mega Battle Deck',
 'ja-ref-671': 'Super Legend Set: Xerneas EX & Yveltal EX',
 'ja-ref-674': 'Hyper Metal Chain Deck',
 'ja-ref-683': 'MCharizard EX Mega Battle Deck',
 'ja-ref-734': "Team Plasma's Powered Half Deck",
 'ja-ref-742': 'National Pokédex Beginning Set',
 'ja-ref-758': 'Battle Gift Set: Thundurus vs Tornadus',
 'ja-ref-768': 'Beginning Set Plus',
 'ja-ref-772': 'Battle Theme Deck: Victini',
 'ja-ref-788': 'Collection Sheet Journey Partners',
 'ja-ref-800': 'Blastoise Battle Starter Deck',
 'ja-ref-802': 'Magmortar Battle Starter Deck',
 'ja-ref-804': 'Raichu Battle Starter Deck',
 'ja-ref-806': 'Torterra Battle Starter Deck',
 'ja-ref-808': 'Leafeon Expert Deck',
 'ja-ref-810': 'Metagross Expert Deck',
 'ja-ref-816': 'L-P Promos',
 'ja-ref-832': 'Charizard SP Half Deck',
 'ja-ref-834': 'Garchomp SP Half Deck',
 'ja-ref-838': 'Gallade SP Half Deck',
 'ja-ref-840': 'Infernape SP Half Deck',
 'ja-ref-842': 'Chimchar DPt Half Deck',
 'ja-ref-844': 'Pikachu DPt Half Deck',
 'ja-ref-846': 'Piplup DPt Half Deck',
 'ja-ref-848': 'Turtwig DPt Half Deck',
 'ja-ref-850': 'Dialga DPt Half Deck',
 'ja-ref-852': 'Giratina DPt Half Deck',
 'ja-ref-854': 'Palkia DPt Half Deck',
 'ja-ref-858': 'DPt Promos',
 'ja-ref-860': 'Dialga Half Deck',
 'ja-ref-862': 'Giratina Half Deck',
 'ja-ref-889': 'Bastiodon the Defender',
 'ja-ref-890': 'Rampardos the Attacker',
 'ja-ref-894': 'DP Promos',
 'ja-ref-989': 'Gift Box Latias ex',
 'ja-ref-991': 'Gift Box Latios ex',
 'ja-ref-997': 'Magma VS Aqua: Two Ambitions',
 'ja-ref-1044': 'Intro Pack Neo Chikorita',
 'ja-ref-1046': 'Intro Pack Neo Totodile',
 'ja-ref-1063': 'Intro Pack Bulbasaur',
 'ja-ref-1065': 'Intro Pack Squirtle',
 'ja-ref-1070': 'Guren Town Gym',
 'ja-ref-1071': 'Yamabuki City Gym',
 'ja-ref-1081': 'Kuchiba City Gym',
 'ja-ref-1083': 'Tamamushi City Gym',
 'ja-ref-1084': 'Hanada City Gym',
 'ja-ref-1086': 'Nivi City Gym',
 'ja-ref-1155': 'Southern Islands JP',
}
# These are broader than the checklist group. Never auto-promote them as exact scopes.
SHARED = {
 'ja-ref-774': 'Battle Strength Decks', 'ja-ref-776': 'Battle Strength Decks', 'ja-ref-778': 'Battle Strength Decks',
 'ja-ref-708': 'Mewtwo vs Genesect Deck Kit', 'ja-ref-710': 'Mewtwo vs Genesect Deck Kit',
 'ja-ref-391': 'VMAX Starter Decks', 'ja-ref-394': 'VMAX Starter Decks', 'ja-ref-364': 'VMAX Starter Decks',
 'ja-ref-415': 'Sword & Shield Starter Decks', 'ja-ref-418': 'Sword & Shield Starter Decks',
 'ja-ref-421': 'Sword & Shield Starter Decks', 'ja-ref-424': 'Sword & Shield Starter Decks', 'ja-ref-427': 'Sword & Shield Starter Decks',
 'ja-ref-869': 'Heatran vs Regigigas Deck Kit', 'ja-ref-870': 'Heatran vs Regigigas Deck Kit',
 'ja-ref-879': 'Magmortar vs Electivire Deck Kit', 'ja-ref-880': 'Magmortar vs Electivire Deck Kit',
 'ja-ref-963': 'Gift Box Emerald', 'ja-ref-965': 'Gift Box Emerald',
 'ja-ref-1099': 'Expansion Sheet', 'ja-ref-1102': 'Expansion Sheet', 'ja-ref-1105': 'Expansion Sheet',
}

SHARED.update({**{f'ja-ref-{i}': 'Gift Box Mew • Lucario' for i in (915,917,919,921,923)},
               **{f'ja-ref-{i}': 'Master Kit' for i in (933,935,937)},
               **{f'ja-ref-{i}': 'Quick Construction Packs' for i in (951,953,955,957,959,961)}})
MULTI = {
 'ja-ref-883': ['Dialga LV.X Constructed Standard Deck', 'Palkia LV.X Constructed Standard Deck'],
 'ja-ref-888': ['Bastiodon the Defender', 'Rampardos the Attacker'],
 'ja-ref-1140': ['Moonlit Pursuit', 'Dawn Dash'],
}
POOLS = {
 **{f'ja-ref-{i}': ['Unnumbered Energies'] for i in range(1127,1136)},
 **{f'ja-ref-{i}': ['Unnumbered Promos'] for i in (1053,1057,1061,1153,1157)},
 'ja-ref-1073': ['Expansion Sheet','Unnumbered Promos'],
 'ja-ref-1076': ['Expansion Sheet','Unnumbered Promos'],
 'ja-ref-1021': ['Pokémon Card VS'],
 'ja-ref-1038': ['Base Expansion Pack'],
 'ja-ref-897': ['Space-Time Creation'],
 'ja-ref-1156': ['Nivi City Gym', 'Guren Town Gym', 'Yamabuki City Gym', 'Kuchiba City Gym',
                 'Tamamushi City Gym', 'Hanada City Gym', 'Expansion Pack', 'Unnumbered Promos'],
}


def normalized(name: str) -> str:
    name = unicodedata.normalize('NFKD', name).casefold()
    return re.sub(r'[^a-z0-9]', '', ''.join(c for c in name if not unicodedata.combining(c)))


def discover(registry, seeds, expansions, source: str):
    by_name = defaultdict(list)
    for entry in expansions:
        by_name[normalized(entry['name'])].append(entry)
    existing = {s['group_id']: s for s in seeds}
    reviewed = []
    for group in registry:
        gid = group['group_id']
        if gid in existing:
            reviewed.append({'group_id': gid, 'state': 'seeded_previously', 'url': existing[gid]['url'],
                             'code': group['code'], 'name': group['name']})
            continue
        if gid in MULTI or gid in POOLS:
            titles = MULTI.get(gid, POOLS.get(gid))
            candidates = [x for title in titles for x in by_name.get(normalized(title), [])]
            reviewed.append({'group_id': gid, 'code': group['code'], 'name': group['name'],
                             'state': 'multi_listing_group_requires_union' if gid in MULTI else 'broad_pool_needs_card_match',
                             'candidates': candidates, 'source': source,
                             'note': 'Observed provider pools only; exact card membership/printing is NOT established'})
            continue
        name = SHARED.get(gid, ALIASES.get(gid, group['name']))
        candidates = by_name.get(normalized(name), [])
        # A title appearing more than once (different locales/editions) is not automatically unique.
        unique = {x['url']: x for x in candidates}
        record = {'group_id': gid, 'code': group['code'], 'name': group['name'],
                  'searched_title': name, 'source': source, 'candidates': list(unique.values())}
        if gid in SHARED and unique:
            record['state'] = 'shared_listing_needs_partition'
        elif len(unique) == 1:
            candidate = next(iter(unique.values()))
            basis = 'reviewed_title_alias' if gid in ALIASES else 'normalized_exact_title'
            existing[gid] = {'group_id': gid, 'url': candidate['url'],
                             'source': f'{source}; {basis}: {group["name"]} → {candidate["name"]}; printing codes still require reconciliation'}
            record.update(state='new_collection_route', mapping_basis=basis, url=candidate['url'])
        elif unique:
            record['state'] = 'ambiguous_title'
        else:
            record['state'] = 'not_matched_in_master_index'
        reviewed.append(record)
    return [existing[g['group_id']] for g in registry if g['group_id'] in existing], reviewed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='append unambiguous collection routes; preserve existing seeds')
    args = parser.parse_args()
    index_path = RUN / 'source-pages/cardmarket-master-index.json'
    index = json.loads(index_path.read_text())
    if not index.get('expansions'):
        raise SystemExit('Master index contains no expansion links; do not infer URLs')
    registry = json.loads((RUN/'set-registry.json').read_text())
    seeds = json.loads((RUN/'listing-seeds.json').read_text())
    digest = hashlib.sha256(index_path.read_bytes()).hexdigest()
    source = f'{index_path.relative_to(RUN)} sha256:{digest}'
    merged, review = discover(registry, seeds, index['expansions'], source)
    counts = dict(sorted((state, sum(x['state']==state for x in review)) for state in {x['state'] for x in review}))
    report = {'observed_at': datetime.now(timezone.utc).isoformat(), 'source_url': 'https://www.cardmarket.com/en/Pokemon/Expansions',
              'source_sha256': digest, 'index_expansions': len(index['expansions']), 'groups': len(registry),
              'previous_seeds': len(seeds), 'proposed_seeds': len(merged), 'states': counts, 'review': review}
    write_json(RUN/'seed-discovery-review.json', report)
    write_json(RUN/'proposed-listing-seeds.json', merged)
    candidate_queue = {}
    for row in review:
        if row['state'] in {'shared_listing_needs_partition', 'multi_listing_group_requires_union', 'broad_pool_needs_card_match'}:
            for candidate in row.get('candidates', []):
                entry = candidate_queue.setdefault(candidate['url'], {'url': candidate['url'], 'name': candidate['name'],
                                                   'group_ids': [], 'state': 'needs_checklist_partition_before_mapping'})
                entry['group_ids'].append(row['group_id'])
    write_json(RUN/'shared-listing-review-queue.json', list(candidate_queue.values()))
    if args.apply:
        backup = RUN / 'refresh-backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        write_json(backup/'listing-seeds.json', seeds)
        write_json(RUN/'listing-seeds.json', merged)
    print(json.dumps({k:v for k,v in report.items() if k!='review'},indent=2))


if __name__=='__main__': main()
