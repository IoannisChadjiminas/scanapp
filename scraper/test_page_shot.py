import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from page_shot import debug_port, page_target


def test_debug_port_reads_chromes_flag():
    assert debug_port(["chrome", "--remote-debugging-port=9222"]) == 9222
    assert debug_port(["chrome"]) is None
    assert debug_port(["chrome", "--remote-debugging-port=nope"]) is None


def test_page_target_prefers_the_http_tab():
    listing = [
        {"type": "page", "url": "about:blank", "title": ""},
        {"type": "iframe", "url": "https://challenges.cloudflare.com/x", "title": "x"},
        {"type": "page", "url": "https://www.cardmarket.com/en", "title": "Just a moment..."},
    ]
    assert page_target(listing)["title"] == "Just a moment..."
    assert page_target([{"type": "page", "url": "about:blank", "title": "New Tab"}])["title"] == "New Tab"
    assert page_target([]) is None
