"""Strict extraction of singles links from a Cardmarket expansion page."""

from __future__ import annotations

import re

from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

from allow import cardmarket_expansion_listing


class _Anchors(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, str]] = []
        self.page_links: list[str] = []
        self._current: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag != "a":
            return
        attr = dict(attrs)
        href = attr.get("href", "")
        if href:
            self.page_links.append(href)
        parts = urlsplit(href)
        bits = [bit for bit in parts.path.split("/") if bit]
        if href:
            product_id = next((attr[key] for key in ("data-product-id", "data-id-product", "idProduct")
                               if attr.get(key, "").isdecimal()), "")
            self._current = {"href": href, "name": "", "product_id": product_id}

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["name"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current is not None:
            self._current["name"] = " ".join(self._current["name"].split())
            self.items.append(self._current)
            self._current = None


def parse_expansion_listing(request_url: str, html: str) -> dict:
    """Return page evidence; invalid/challenge/wrong-expansion pages never look empty."""
    if not cardmarket_expansion_listing(request_url):
        return {"outcome": "wrong_product", "products": []}
    lowered = (html or "").lower()
    if any(marker in lowered for marker in ("just a moment", "cf-turnstile", "challenge-form", "verify you are human")):
        return {"outcome": "challenge_unsolved", "products": []}
    requested = urlsplit(request_url)
    requested_query = parse_qs(requested.query)
    numeric_listing = requested.path.rstrip("/").casefold().endswith("/products/singles")
    expected = None if numeric_listing else requested.path.rstrip("/").split("/")[-1].casefold()
    parser = _Anchors()
    parser.feed(html or "")
    if requested.path.rstrip("/").casefold().endswith("/pokemon/expansions"):
        expansions = {}
        for item in parser.items:
            absolute = urljoin(request_url, item["href"])
            parts = urlsplit(absolute)
            bits = parts.path.strip("/").split("/")
            if (len(bits) == 4 and bits[1:3] == ["Pokemon", "Expansions"]
                    and cardmarket_expansion_listing(absolute)):
                expansions[absolute] = {"url": absolute, "name": item["name"]}
        return {"outcome": "listing_links" if expansions else "wrong_product", "products": [],
                "listing_urls": list(expansions), "expansions": list(expansions.values())}
    products = []
    seen = set()
    for item in parser.items:
        absolute = urljoin(request_url, item["href"])
        parts = urlsplit(absolute)
        bits = [bit for bit in parts.path.split("/") if bit]
        if parts.scheme != "https" or parts.netloc.lower() not in {"www.cardmarket.com", "cardmarket.com"}:
            continue
        if (len(bits) < 6 or [part.casefold() for part in bits[1:4]] != ["pokemon", "products", "singles"]
                or (expected is not None and bits[4].casefold() != expected)):
            continue
        absolute = urlunsplit(("https", "www.cardmarket.com", parts.path.rstrip("/"), "", ""))
        name = re.sub(r"\s*From\s+\d.*$", "", item["name"]).strip() or bits[-1].replace("-", " ")
        key = absolute
        if key in seen:
            continue
        seen.add(key)
        product = {"url": absolute, "name": name}
        if item.get("product_id"):
            product["product_id"] = item["product_id"]
        products.append(product)
    pagination = []
    for href in parser.page_links:
        absolute = urljoin(request_url, href)
        parts = urlsplit(absolute)
        bits = [bit for bit in parts.path.split("/") if bit]
        query = parse_qs(parts.query)
        same_group = (
            numeric_listing and parts.path.rstrip("/").casefold() == requested.path.rstrip("/").casefold()
            and query.get("idExpansion") == requested_query.get("idExpansion")
        ) or (
            not numeric_listing and bits and bits[-1].casefold() == expected
        )
        if (cardmarket_expansion_listing(absolute) and same_group
                and any(query.get(key, [""])[0].isdecimal() for key in ("page", "site"))):
            # Keep filters fixed: a pagination control must not broaden the requested set/language.
            fixed = {k: v for k, v in requested_query.items() if k not in {"page", "site"}}
            candidate = {k: v for k, v in query.items() if k not in {"page", "site"}}
            if candidate == fixed:
                canonical = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
                if canonical != urlunsplit((requested.scheme, requested.netloc, requested.path, requested.query, "")):
                    pagination.append(canonical)
    listing_urls = []
    for href in parser.page_links:
        absolute = urljoin(request_url, href)
        parts = urlsplit(absolute)
        bits = [bit for bit in parts.path.split("/") if bit]
        if (expected is not None and len(bits) == 5 and bits[-1].casefold() == expected
                and [b.casefold() for b in bits[1:4]] == ["pokemon", "products", "singles"]
                and cardmarket_expansion_listing(absolute)):
            listing_urls.append(absolute)
    if products:
        return {"outcome": "offers", "products": products, "pagination_urls": list(dict.fromkeys(pagination))}
    if any(marker in lowered for marker in ("data-test-empty", "no products in this expansion", "no products found")):
        return {"outcome": "empty", "products": [], "pagination_urls": []}
    return {"outcome": "listing_links" if listing_urls else "wrong_product", "products": [],
            "pagination_urls": [], "listing_urls": list(dict.fromkeys(listing_urls))}
