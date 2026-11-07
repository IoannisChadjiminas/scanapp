"""Run safe Pooka number/name matches for older Japanese sets and promos."""
from __future__ import annotations

import subprocess
import sys
import urllib.parse

SCRIPT = "api/scripts/ja_set_recovery/acquire_pooka_numbered_set.py"
JOBS = [
    ("ja-ref-894", "ja-dpp", "Diamond & Pearl Promos"),
    ("ja-ref-892", "ja-dp2", "Secret of the Lakes"),
    ("ja-ref-896", "ja-dp1", "Space-Time Creation"),
    ("ja-ref-886", "ja-dp3", "Shining Darkness"),
    ("ja-ref-830", "ja-dpt3", "Beat of the Frontier"),
    ("ja-ref-856", "ja-dpt1", "Galactic's Conquest"),
    ("ja-ref-864", "ja-dps", "Intense Fight in the Destroyed Sky"),
    ("ja-ref-816", "ja-lp", "LEGEND Promos"),
    ("ja-ref-818", "ja-dpt4", "Advent of Arceus"),
    ("ja-ref-836", "ja-dpt2", "Bonds to the End of Time"),
    ("ja-ref-858", "ja-dptp", "Platinum Promos"),
    ("ja-ref-872", "ja-dp5", "Temple of Anger"),
    ("ja-ref-1007", "ja-adv-expansion-pack", "ADV Expansion Pack"),
    ("ja-ref-1005", "ja-miracle-of-the-desert", "Miracle of the Desert"),
    ("ja-ref-997", "ja-magma-vs-aqua-two-ambitions", "Magma vs Aqua: Two Ambitions"),
    ("ja-ref-1001", "ja-rulers-of-the-heavens", "Rulers of the Heavens"),
    ("ja-ref-987", "ja-undone-seal", "Undone Seal"),
    ("ja-ref-1015", "ja-adv-promos", "ADV Promos"),
    ("ja-ref-1018", "ja-pok-mon-web", "Pokémon Web"),
    ("ja-ref-706", "ja-ebb", "EX Battle Boost"),
    ("ja-ref-790", "ja-l3", "Clash at the Summit"),
    ("ja-ref-794", "ja-l2", "Reviving Legends"),
    ("ja-ref-1148", "ja-play-promos", "PLAY Promos"),
    ("ja-ref-1150", "ja-mcdonald-s-pok-mon-e-minimum-pack", "McDonald's Pokémon-e Minimum Pack"),
    ("ja-ref-1044", "ja-intro-pack-neo-chikorita-", "Intro Pack Neo (Chikorita)"),
    ("ja-ref-1046", "ja-intro-pack-neo-totodile-", "Intro Pack Neo (Totodile)"),
    ("ja-ref-1063", "ja-intro-pack-bulbasaur-", "Intro Pack (Bulbasaur)"),
    ("ja-ref-1065", "ja-intro-pack-squirtle-", "Intro Pack (Squirtle)"),
    ("ja-ref-1083", "ja-tamamushi-city-gym-deck", "Tamamushi City Gym Deck"),
    ("ja-ref-897", "ja-dp1", "Space-Time Creation"),
    ("ja-ref-519", "ja-smg", "Ultra Sun & Ultra Moon Deck Build Boxes"),
    ("ja-ref-758", "ja-bgs", "Thundurus vs Tornadus Battle Gift Set"),
    ("ja-ref-671", "ja-xyc", "Xerneas-EX & Yveltal-EX Super Legend Set"),
    ("ja-ref-1108", "ja-movie-commemoration-random-pack", "Movie Commemoration Random Pack"),
    ("ja-ref-612", "ja-xyh", "M Audino-EX Mega Battle Deck"),
    ("ja-ref-647", "ja-xye", "Emboar-EX vs Togekiss-EX Deck Kit"),
    ("ja-ref-1042", "ja-p-promos", "P Promos"),
    ("ja-ref-1071", "ja-yamabuki-city-gym-deck", "Yamabuki City Gym Deck"),
    ("ja-ref-1086", "ja-nivi-city-gym-deck", "Nivi City Gym Deck"),
    ("ja-ref-1152", "ja-t-promos", "T Promos"),
    ("ja-ref-772", "ja-btv", "Victini Battle Theme Deck"),
    ("ja-ref-1070", "ja-guren-town-gym-deck", "Guren Town Gym Deck"),
    ("ja-ref-1081", "ja-kuchiba-city-gym-deck", "Kuchiba City Gym Deck"),
    ("ja-ref-1084", "ja-hanada-city-gym-deck", "Hanada City Gym Deck"),
    ("ja-ref-1116", "ja-movie-commemoration-vs-pack-auras-lucario", "Movie Commemoration VS Pack: Aura's Lucario"),
    ("ja-ref-1118", "ja-movie-commemoration-vs-pack-sky-splitting-deoxys", "Movie Commemoration VS Pack: Sky-Splitting Deoxys"),
    ("ja-ref-1120", "ja-movie-commemoration-vs-pack", "Movie Commemoration VS Pack"),
    ("ja-ref-1122", "ja-theater-limited-vs-pack", "Theater Limited VS Pack"),
    ("ja-ref-683", "ja-xya", "M Charizard-EX Mega Battle Deck"),
    ("ja-ref-615", "ja-xyg", "Zygarde-EX Perfect Battle Deck"),
    ("ja-ref-659", "ja-xyd", "M Rayquaza-EX Mega Battle Deck"),
    ("ja-ref-1021", "ja-pok-mon-vs", "Pokémon VS"),
    ("ja-ref-674", "ja-xyb", "Dialga-EX + Aegislash-EX Hyper Metal Chain Deck"),
    ("ja-ref-967", "ja-black-deck-kit", "Black Deck Kit"),
    ("ja-ref-1099", "ja-vending-machine-series-3-green-", "Vending Machine Series 3 (Green)"),
    ("ja-ref-1102", "ja-vending-machine-series-2-red-", "Vending Machine Series 2 (Red)"),
    ("ja-ref-1105", "ja-vending-machine-series-1-blue-", "Vending Machine Series 1 (Blue)"),
    ("ja-ref-1156", "ja-miscellaneous-decks", "Miscellaneous Decks"),
    ("ja-ref-710", "ja-mg", "Mewtwo vs Genesect Deck Kit (Mewtwo)"),
    ("ja-ref-712", "ja-k+k", "Blastoise + Kyurem-EX Combo Deck"),
    ("ja-ref-1153", "ja-pok-mon-vs", "Pokémon VS"),
    ("ja-ref-957", "ja-lightning-quick-construction-pack", "Lightning Quick Construction Pack"),
    ("ja-ref-951", "ja-fighting-quick-construction-pack", "Fighting Quick Construction Pack"),
    ("ja-ref-953", "ja-fire-quick-construction-pack", "Fire Quick Construction Pack"),
    ("ja-ref-955", "ja-grass-quick-construction-pack", "Grass Quick Construction Pack"),
    ("ja-ref-959", "ja-psychic-quick-construction-pack", "Psychic Quick Construction Pack"),
    ("ja-ref-961", "ja-water-quick-construction-pack", "Water Quick Construction Pack"),
    ("ja-ref-941", "ja-mirage-s-mew-constructed-starter-deck", "Mirage's Mew Constructed Starter Deck"),
    ("ja-ref-824", "ja-dptm", "Mewtwo LV.X Collection Pack"),
    ("ja-ref-826", "ja-dptr", "Regigigas LV.X Collection Pack"),
    ("ja-ref-828", "ja-dpts", "Shaymin LV.X Collection Pack"),
    ("ja-ref-812", "ja-l1-bhg", "HeartGold Collection"),
    ("ja-ref-808", "ja-e", "Leafeon vs Metagross Expert Deck (Leafeon)"),
    ("ja-ref-1155", "ja-southern-islands", "Southern Islands"),
    ("ja-ref-927", "ja-holon-research-tower-fire-quarter-deck", "Holon Research Tower Fire Quarter Deck"),
    ("ja-ref-1112", "ja-10th-movie-commemoration-set", "10th Movie Commemoration Set"),
    ("ja-ref-626", "ja-xyf", "Golduck BREAK + Palkia-EX Combo Deck"),
    ("ja-ref-1139", "ja-melee-pok-mon-scramble", "Melee! Pokémon Scramble"),
    ("ja-ref-298", "ja-s8b", "VMAX Climax"),
    ("ja-ref-557", "ja-sm2+", "Facing a New Trial"),
    ("ja-ref-581", "ja-smb", "Premium Trainer Box"),
    ("ja-ref-804", "ja-b", "Battle Starter Deck (Torterra)"),
    ("ja-ref-435", "ja-sm12a", "Tag All Stars"),
]


def main() -> None:
    for group_id, slug, label in JOBS:
        page_url = "https://pooka.app/list/set/cards/" + slug + "/" + urllib.parse.quote(label, safe="")
        output = (
            f"pooka-{group_id}-number-only-image-acquisition-20261030.json"
            if group_id == "ja-ref-435" else
            f"pooka-{group_id}-image-acquisition-20261030.json"
        )
        command = [
            sys.executable, SCRIPT,
            "--group-id", group_id,
            "--set-slug", slug,
            "--set-label", label,
            "--page-url", page_url,
            "--output-name", output,
            "--match-number-only" if group_id == "ja-ref-435" else
            "--match-number-and-name", "--also-unique-name",
        ]
        if group_id == "ja-ref-1139":
            command.append("--ignore-level-suffix")
        print(f"Starting {group_id} ({label})", flush=True)
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
