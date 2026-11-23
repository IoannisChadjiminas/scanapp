"""English titles of Japanese expansions.

`set_name` is the catalogue's own title, used for matching. `set_view_title`
is the English title shown to the user, as `view_title` is for a card's name.
Matching must not read it.

The catalogue names 124 Japanese expansions in Japanese. Their English
titles follow Cardmarket's names for them, with the capitals and punctuation
its URLs drop restored. Expansions the catalogue already names in English
have no entry.
"""

from __future__ import annotations

import re

JA_SET_TITLES: dict[str, str] = {
    "M6": "Storm Emeralda",
    "M5": "Abyss Eye",
    "M4": "Ninja Spinner",
    "M3": "Nihil Zero",
    "MC": "MEGA Start Deck 100 Battle Collection",
    "M2a": "MEGA Dream ex",
    "M2": "Inferno X",
    "M1S": "Mega Symphonia",
    "M1L": "Mega Brave",
    "M-P": "M-P Promos",
    "SV11B": "Black Bolt",
    "SV11W": "White Flare",
    "SV10": "The Glory of Team Rocket",
    "SV9a": "Heat Wave Arena",
    "SV9": "Battle Partners",
    "SV8a": "Terastal Festival ex",
    "SV8": "Super Electric Breaker",
    "SV7a": "Paradise Dragona",
    "SVLS": "Stellar Tera Type Starter Set: Ceruledge ex",
    "SVLN": "Stellar Tera Type Starter Set: Sylveon ex",
    "SV7": "Stellar Miracle",
    "SVK": "Stellar Miracle Deck Build Box",
    "SV6a": "Night Wanderer",
    "SV6": "Mask of Change",
    "SV5a": "Crimson Haze",
    "SV5M": "Cyber Judge",
    "SV5K": "Wild Force",
    "SV4a": "Shiny Treasure ex",
    "SV4K": "Ancient Roar",
    "SV4M": "Future Flash",
    "SV3a": "Raging Surf",
    "SV3": "Ruler of the Black Flame",
    "SV2a": "Pokémon Card 151",
    "SV2D": "Clay Burst",
    "SV2P": "Snow Hazard",
    "SV1a": "Triplet Beat",
    "SV1S": "Scarlet ex",
    "SV1V": "Violet ex",
    "S12a": "VSTAR Universe",
    "SV-P": "Scarlet & Violet Promos",
    "S12": "Paradigm Trigger",
    "S11a": "Incandescent Arcana",
    "S11": "Lost Abyss",
    "S10a": "Dark Phantasma",
    "S10P": "Space Juggler",
    "S9a": "Battle Region",
    "S9": "Star Birth",
    "S8b": "VMAX Climax",
    "S8a": "25th Anniversary Collection",
    "S8": "Fusion Arts",
    "S7D": "Towering Perfection",
    "S6K": "Jet-Black Spirit",
    "S6H": "Silver Lance",
    "S5I": "Single Strike Master",
    "SM12a": "Tag All Stars",
    "SM12": "Alter Genesis",
    "SM11b": "Dream League",
    "SM11a": "Remix Bout",
    "SM11": "Miracle Twin",
    "SM10b": "Sky Legend",
    "SM10a": "GG End",
    "SM10": "Double Blaze",
    "SM9b": "Full Metal Wall",
    "SM9a": "Night Unison",
    "SM9": "Tag Bolt",
    "SM8b": "GX Ultra Shiny",
    "SM8a": "Dark Order",
    "SM8": "Super-Burst Impact",
    "SM7b": "Fairy Rise",
    "SM7a": "Thunderclap Spark",
    "SM7": "Sky-Splitting Charisma",
    "SM6b": "Champion Road",
    "SM6a": "Dragon Storm",
    "SM6": "Forbidden Light",
    "SM5p": "Ultra Force",
    "SM5S": "Ultra Sun",
    "SM5M": "Ultra Moon",
    "SM4p": "GX Battle Boost",
    "SM4S": "Awakened Heroes",
    "SM4A": "Ultradimensional Beasts",
    "SM3p": "Shining Legends",
    "SM3N": "Darkness that Consumes Light",
    "SM3H": "To Have Seen the Battle Rainbow",
    "SM2p": "Facing a New Trial",
    "SM2L": "Alolan Moonlight",
    "SM2K": "Islands Await You",
    "SM1p": "Strength Expansion Pack Sun & Moon",
    "SM1S": "Collection Sun",
    "SM1M": "Collection Moon",
    "XY10": "Awakening Psychic King",
    "CP2": "Legendary Shine Collection",
    "XY7": "Bandit Ring",
    "CP1": "Magma Gang vs Aqua Gang: Double Crisis",
    "XY3": "Rising Fist",
    "PCG9": "Offense and Defense of the Furthest Ends",
    "PCG8": "Miracle Crystal",
    "PCG7": "Holon Phantom",
    "PCG6": "Holon Research Tower",
    "PCG5": "Mirage Forest",
    "PCG4": "Golden Sky, Silvery Ocean",
    "PCG3": "Rocket Gang Strikes Back",
    "PCG2": "Clash of the Blue Sky",
    "PCG1": "Flight of Legends",
    "E5": "Mysterious Mountains",
    "E4": "Split Earth",
    "E3": "Wind from the Sea",
    "E2": "The Town on No Map",
    "E1": "Base Expansion Pack",
    "web1": "Pokémon Card web",
    "VS1": "Pokémon Card VS",
    "neo4": "Darkness, and to Light...",
    "neo3": "Awakening Legends",
    "neo2": "Crossing the Ruins...",
    "neo1": "Gold, Silver, to a New World...",
    "PMCG6": "Challenge from the Darkness",
    "PMCG5": "Leaders' Stadium",
    "PMCG4": "Rocket Gang",
    "PMCG3": "Mystery of the Fossils",
    "PMCG2": "Pokémon Jungle",
    "PMCG1": "Expansion Pack",
    "L1SS": "SoulSilver Collection",
    "L1HG": "HeartGold Collection",
    "S8a-P": "25th Anniversary Edition",
    "WCP": "World Champions Pack",
}

_CARD_SET = re.compile(r"^ja:(.+)-[^-]+$")


def set_view_title(language: str | None, set_id: str | None) -> str | None:
    """The English title shown for an expansion, where it has one."""
    if language != "ja" or not set_id:
        return None
    return JA_SET_TITLES.get(set_id)


def card_set_view_title(card_id: str | None, language: str | None = None) -> str | None:
    """[set_view_title] of a card's expansion, read from its id
    (`ja:SV10-001`)."""
    match = _CARD_SET.match(card_id or "")
    if not match or (language and language != "ja"):
        return None
    return JA_SET_TITLES.get(match.group(1))


def ja_sets_titled(tokens: list[str]) -> tuple[list[str], list[str]]:
    """The Japanese expansions whose English title has every one of the
    `tokens` that match a word of it, and those tokens. A token of at least
    three letters matches a title word it starts. Empty when no title has
    one."""
    words = {sid: re.findall(r"[a-z0-9]+", title.casefold()) for sid, title in JA_SET_TITLES.items()}
    best: tuple[list[str], list[str]] = ([], [])
    for sid, title_words in words.items():
        used = [token for token in tokens
                if len(token) >= 3 and any(word.startswith(token.casefold()) for word in title_words)]
        if not used:
            continue
        if len(used) > len(best[1]):
            best = ([sid], used)
        elif len(used) == len(best[1]) and used == best[1]:
            best[0].append(sid)
    return best
