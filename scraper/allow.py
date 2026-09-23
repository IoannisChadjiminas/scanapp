from urllib.parse import urlsplit


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
