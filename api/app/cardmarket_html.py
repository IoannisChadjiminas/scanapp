"""Parse a Cardmarket product page the phone already loaded.

The phone sends the URL and HTML. This service does not fetch Cardmarket.
Selector changes stay here so the app does not need a new release.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

PARSER_VERSION = "offers-html-v1"
MAX_ROWS = 6

_VOID = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)
_SKIP_TEXT = frozenset({"script", "style", "noscript"})
_MONEY_RE = re.compile(
    r"(?:€\s*)?(?:\d{1,3}(?:[.\s]\d{3})*[,.]\d{2}|\d+[,.]\d{2})\s*(?:€|EUR)",
    re.IGNORECASE,
)
_CONDITION_RE = re.compile(
    r"^(NM|M|EX|GD|LP|PL|PO|SS|MT|Near Mint|Excellent|Mint)$",
    re.IGNORECASE,
)
_LANGUAGE_RE = re.compile(
    r"^(English|German|French|Italian|Spanish|Portuguese|Japanese|Korean|"
    r"Chinese|Traditional Chinese|Simplified Chinese|Dutch|Polish|Russian|"
    r"Czech|Hungarian|Greek)$",
    re.IGNORECASE,
)
_VARIANT_RE = re.compile(
    r"^(Reverse Holo|Holo|Foil|Reverse Holofoil|First Edition|1st Edition|"
    r"Unlimited|Normal)$",
    re.IGNORECASE,
)
_CHALLENGE_IDS = frozenset(
    {"challenge-form", "cf-challenge", "challenge-running", "cf-chl-widget"}
)
_CHALLENGE_CLASSES = frozenset({"cf-turnstile", "cf-browser-verification"})
_OFFER_CLASSES = frozenset(
    {"col-offer", "price-container", "mobile-offer-container", "listing-price"}
)
_PRICE_CLASSES = frozenset({"price-container", "listing-price"})
_COUNT_CLASS_RE = re.compile(r"comment|quantity|item-count|available", re.IGNORECASE)
_EMPTY_RE = re.compile(
    r"there are currently no articles|no articles available|there are no articles",
    re.IGNORECASE,
)
_CHALLENGE_RE = re.compile(
    r"just a moment|einen moment|attention required|verify you are human|"
    r"checking your browser",
    re.IGNORECASE,
)
_SALES_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*([kK])?\s+sales",
    re.IGNORECASE,
)
_HEADER_MONEY = {
    "From": re.compile(r"From\s*([0-9][0-9.\s]*,\d{2})\s*€", re.IGNORECASE),
    "Trend": re.compile(r"Price Trend\s*([0-9][0-9.\s]*,\d{2})\s*€", re.IGNORECASE),
    "7-day": re.compile(
        r"7-days average price\s*([0-9][0-9.\s]*,\d{2})\s*€", re.IGNORECASE
    ),
    "30-day": re.compile(
        r"30-days average price\s*([0-9][0-9.\s]*,\d{2})\s*€", re.IGNORECASE
    ),
}
_AVAILABLE_RE = re.compile(r"Available items\s*(\d+)", re.IGNORECASE)


class _Node:
    def __init__(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tag = tag
        self.attrs = {key.lower(): value or "" for key, value in attrs}
        self.children: list[_Node] = []
        self.parent: _Node | None = None
        self.parts: list[str] = []

    def classes(self) -> set[str]:
        return {item for item in self.attrs.get("class", "").split() if item}

    def attr(self, name: str) -> str:
        return self.attrs.get(name.lower(), "")

    def text(self) -> str:
        chunks: list[str] = []

        def walk(node: _Node) -> None:
            chunks.extend(node.parts)
            for child in node.children:
                walk(child)

        walk(self)
        return re.sub(r"\s+", " ", "".join(chunks)).strip()

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document", [])
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag.lower(), attrs)
        node.parent = self.stack[-1]
        self.stack[-1].children.append(node)
        if node.tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if self.stack[-1].tag in _SKIP_TEXT:
            return
        self.stack[-1].parts.append(data)


def product_path(url: str | None) -> str | None:
    parsed = urlsplit((url or "").strip())
    host = parsed.netloc.lower().split(":")[0]
    if parsed.scheme != "https" or host not in {"www.cardmarket.com", "cardmarket.com"}:
        return None
    path = parsed.path.rstrip("/")
    if "/Products/Singles/" not in path:
        return None
    return path.lower()


def _hidden(node: _Node) -> bool:
    current: _Node | None = node
    while current is not None and current.tag != "document":
        if "hidden" in current.attrs:
            return True
        style = current.attr("style").lower().replace(" ", "")
        if "display:none" in style or "visibility:hidden" in style:
            return True
        if "d-none" in current.classes():
            return True
        current = current.parent
    return False


def _is_row(node: _Node) -> bool:
    classes = node.classes()
    if "article-row" in classes or "article-container" in classes:
        return True
    if node.tag == "tr" and "article" in classes:
        return True
    return node.attr("id").startswith("articleRow")


def _challenge_node(node: _Node) -> bool:
    if node.attr("id") in _CHALLENGE_IDS or node.classes() & _CHALLENGE_CLASSES:
        return True
    if node.tag == "input" and node.attr("name") == "cf-turnstile-response":
        return True
    if node.tag == "iframe":
        src = node.attr("src").lower()
        return "challenges.cloudflare.com" in src or "turnstile" in src
    return False


def _canonical_url(root: _Node) -> str | None:
    for node in root.walk():
        if node.tag == "link" and "canonical" in node.attr("rel").lower():
            href = node.attr("href").strip()
            if href:
                return href
        if node.tag == "meta" and node.attr("property").lower() == "og:url":
            content = node.attr("content").strip()
            if content:
                return content
    return None


def _title(root: _Node) -> str:
    for node in root.walk():
        if node.tag == "title":
            return node.text()[:120]
    return ""


def _count_node(node: _Node) -> bool:
    return bool(_COUNT_CLASS_RE.search(node.attr("class")))


def _price_text(node: _Node) -> str:
    """Offer text without comment or quantity counts.

    Those counts sit in the same cell as the ask. Joining their text nodes
    without a gap turns 1 and 23,36 € into 123,36 €.
    """
    chunks: list[str] = []

    def walk(current: _Node, *, root: bool) -> None:
        if not root and _count_node(current):
            return
        chunks.extend(current.parts)
        chunks.append(" ")
        for child in current.children:
            walk(child, root=False)

    walk(node, root=True)
    return re.sub(r"\s+", " ", "".join(chunks)).strip()


def _offer_price(row: _Node) -> str | None:
    offers = [
        node
        for node in row.walk()
        if node is not row and node.classes() & _OFFER_CLASSES and not _hidden(node)
    ]
    innermost = [
        node
        for node in offers
        if not any(other is not node and other in node.walk() for other in offers)
    ]
    ranked = sorted(
        innermost or offers,
        key=lambda node: 0 if node.classes() & _PRICE_CLASSES else 1,
    )
    for offer in ranked:
        blob = _price_text(offer)
        asking = re.split(r"(?:\+|incl\.?|including)\s*ship", blob, maxsplit=1, flags=re.I)[0]
        match = _MONEY_RE.search(asking)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip()
    return None


def _label(node: _Node) -> str:
    for name in ("data-bs-original-title", "data-original-title", "title", "aria-label"):
        value = node.attr(name).strip()
        if value:
            return value
    return ""


def _rows(root: _Node) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in root.walk():
        if not _is_row(row) or _hidden(row):
            continue
        price = _offer_price(row)
        if not price:
            continue
        condition = ""
        for node in row.walk():
            if node is row:
                continue
            classes = node.classes()
            class_blob = node.attr("class")
            if not (
                "article-condition" in classes
                or "badge" in classes
                or "condition" in class_blob
            ):
                continue
            token = node.text().split(" ")[0] if node.text() else ""
            if _CONDITION_RE.match(token):
                condition = token
                break
        labels = [_label(node) for node in row.walk() if node is not row]
        labels = [value for value in labels if value]
        language = next((value for value in labels if _LANGUAGE_RE.match(value)), "")
        variant = ", ".join(
            dict.fromkeys(value for value in labels if _VARIANT_RE.match(value))
        )
        key = f"{price}|{condition}|{language}|{variant}"
        if key in seen:
            continue
        seen.add(key)
        item = {
            "price": price,
            "condition": condition,
            "language": language,
            "variant": variant,
        }
        sales = _sales_count(row.text())
        if sales is not None:
            item["sales"] = str(sales)
        if _professional_power_seller(row, labels):
            item["seller"] = "Professional Power Seller"
        found.append(item)
        if len(found) == MAX_ROWS:
            break
    return found


def _euro_amount(raw: str) -> float | None:
    number = raw.replace(" ", "").replace("€", "")
    if "," in number and "." in number:
        if number.rfind(",") > number.rfind("."):
            number = number.replace(".", "").replace(",", ".")
        else:
            number = number.replace(",", "")
    else:
        number = number.replace(",", ".")
    try:
        amount = float(number)
    except ValueError:
        return None
    if amount <= 0 or amount > 1_000_000:
        return None
    return amount


def _professional_power_seller(row: _Node, labels: list[str]) -> bool:
    """Both Cardmarket seller badges on this listing."""
    titles = {value.strip().lower() for value in labels}
    professional = "professional" in titles
    power = "power seller" in titles or "powerseller" in titles
    for node in row.walk():
        classes = " ".join(node.classes()).lower()
        if "professional" in classes:
            professional = True
        if "power-seller" in classes or "powerseller" in classes:
            power = True
    return professional and power


def _sales_count(text: str) -> int | None:
    match = _SALES_RE.search(text)
    if not match:
        return None
    number = float(match.group(1).replace(",", "."))
    if match.group(2):
        number *= 1000
    count = int(round(number))
    if count < 0 or count > 10_000_000:
        return None
    return count


def _header(text: str) -> dict[str, float | int]:
    found: dict[str, float | int] = {}
    for label, pattern in _HEADER_MONEY.items():
        match = pattern.search(text)
        if not match:
            continue
        amount = _euro_amount(match.group(1))
        if amount is not None:
            found[label] = amount
    available = _AVAILABLE_RE.search(text)
    if available:
        found["Available"] = int(available.group(1))
    return found


def _empty(root: _Node, text: str) -> bool:
    for node in root.walk():
        if "data-test-empty-articles" in node.attrs:
            return True
        classes = node.classes()
        if "noArticles" in classes or "no-articles" in classes:
            return True
    return bool(_EMPTY_RE.search(text))


def parse_cardmarket_html(url: str, html: str) -> dict:
    """Return the phone reader's offer JSON. `url` is the page the phone loaded."""
    builder = _Builder()
    builder.feed(html)
    builder.close()
    root = builder.root
    title = _title(root)
    text = root.text()[:2500]
    href = url
    blocked = any(_challenge_node(node) for node in root.walk()) or bool(
        _CHALLENGE_RE.search(f"{href} {title} {text}")
    )
    if "/cdn-cgi/" in href.lower():
        blocked = True
    if blocked:
        return {
            "url": url,
            "blocked": True,
            "empty": False,
            "pending": False,
            "rows": [],
            "title": title,
            "parser": PARSER_VERSION,
        }
    canonical = _canonical_url(root)
    expected = product_path(url)
    found = product_path(canonical) if canonical else None
    if expected and found and expected != found:
        return {
            "url": canonical or url,
            "blocked": False,
            "empty": False,
            "pending": False,
            "rows": [],
            "parser": PARSER_VERSION,
        }
    rows = _rows(root)
    empty = _empty(root, text)
    return {
        "url": url,
        "blocked": False,
        "empty": empty,
        "pending": not rows and not empty,
        "rows": rows,
        "header": _header(root.text()),
        "parser": PARSER_VERSION,
    }
