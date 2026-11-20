from urllib.parse import parse_qsl, urlsplit


def cardmarket_product(url: str) -> bool:
    parts = urlsplit((url or "").strip())
    if parts.scheme.lower() != "https":
        return False
    host = parts.netloc.lower().split(":")[0]
    if host not in {"www.cardmarket.com", "cardmarket.com"}:
        return False
    bits = [bit for bit in parts.path.split("/") if bit]
    return (
        len(bits) >= 6
        and bits[1].lower() == "pokemon"
        and bits[2].lower() == "products"
        and bits[3].lower() == "singles"
        and bool(bits[-2] and bits[-1])
    )


_LISTING_PARAMS = {"page", "site", "perPage", "perSite", "mode", "sortBy", "sortDir", "language", "idExpansion", "idRarity"}


def cardmarket_expansion_listing(url: str) -> bool:
    """Allow only Cardmarket Pokémon expansion listings and bounded list filters."""
    parts = urlsplit((url or "").strip())
    if parts.scheme.lower() != "https" or parts.netloc.lower() not in {"www.cardmarket.com", "cardmarket.com"}:
        return False
    bits = [bit for bit in parts.path.split("/") if bit]
    if not bits or bits[0].lower() not in {"en", "de", "fr", "es", "it"}:
        return False
    route = [part.casefold() for part in bits[1:]]
    if route == ["pokemon", "expansions"]:
        return not parts.query and not parts.fragment
    if not ((len(bits) == 4 and route[:2] == ["pokemon", "expansions"])
            or (len(bits) in {4, 5} and route[:3] == ["pokemon", "products", "singles"])):
        return False
    try:
        pairs = parse_qsl(parts.query, keep_blank_values=True, max_num_fields=12)
    except ValueError:
        return False
    if any(key not in _LISTING_PARAMS or not value or len(value) > 40 for key, value in pairs):
        return False
    if len({key for key, _ in pairs}) != len(pairs):
        return False
    for key, value in pairs:
        if key in {"page", "site", "perPage", "perSite", "idExpansion", "idRarity", "language"} and not value.isdecimal():
            return False
        if key == "mode" and value != "list":  # the list view: 50 rows a page, product id on each row
            return False
        if key == "perSite" and int(value) > 50:
            return False
    if len(bits) == 4 and route == ["pokemon", "products", "singles"]:
        return any(key == "idExpansion" for key, _ in pairs)
    return True
