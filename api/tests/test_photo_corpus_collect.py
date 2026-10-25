import csv
import importlib.util
from io import BytesIO
import json
from pathlib import Path

import pytest
from PIL import Image


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "photo_corpus" / "collect.py"
SPEC = importlib.util.spec_from_file_location("photo_corpus_collect", SCRIPT)
collect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collect)


def photo_bytes(width=1200, height=1600):
    image = Image.new("RGB", (width, height), "white")
    body = BytesIO()
    image.save(body, format="JPEG")
    return body.getvalue()


def test_load_credentials_reads_local_file_and_rejects_template(tmp_path):
    path = tmp_path / "ebay.env"
    path.write_text("# local\nEBAY_CLIENT_ID=client\nEBAY_CLIENT_SECRET='secret-value'\n")
    assert collect.load_credentials(path) == ("client", "secret-value")
    path.write_text("EBAY_CLIENT_ID=\nEBAY_CLIENT_SECRET=\n")
    with pytest.raises(ValueError, match="Set EBAY_CLIENT_ID"):
        collect.load_credentials(path)


@pytest.mark.parametrize(("content_type", "url", "expected"), [
    ("image/jpeg; charset=binary", "https://i.ebayimg.com/image", ".jpg"),
    ("image/webp", "https://i.ebayimg.com/image", ".webp"),
    ("text/html", "https://i.ebayimg.com/image.webp", ".webp"),
    ("application/json", "https://example.test/no-image", None),
])
def test_image_extension(content_type, url, expected):
    assert collect.image_extension(content_type, url) == expected


def test_item_id_from_url_handles_both_listing_forms():
    assert collect.item_id_from_url("https://www.ebay.com/itm/123456789012") == "123456789012"
    assert collect.item_id_from_url("https://www.ebay.com/itm/Charizard/123456789012?foo=bar") == "123456789012"
    assert collect.item_id_from_url("https://example.test/no-item") is None


def test_full_size_image_url_upgrades_browse_image_and_fails_closed():
    assert collect.full_size_image_url(
        "https://i.ebayimg.com/images/g/example/s-l225.jpg?x=1"
    ) == "https://i.ebayimg.com/images/g/example/s-l1600.jpg?x=1"
    with pytest.raises(ValueError, match="size token"):
        collect.full_size_image_url("https://i.ebayimg.com/images/g/example/photo.jpg")
    with pytest.raises(ValueError, match="HTTPS eBay"):
        collect.full_size_image_url("https://example.test/images/s-l225.jpg")


@pytest.mark.parametrize(("width", "height", "accepted"), [(1200, 900, True), (999, 300, False)])
def test_image_dimensions_and_minimum_long_edge(width, height, accepted):
    actual = collect.image_dimensions(photo_bytes(width, height))
    assert actual == (width, height)
    assert (max(actual) >= collect.MIN_LONG_EDGE) is accepted


class Response:
    def __init__(self, status_code, payload=None, content=b"", headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self):
        self.posts = []
        self.gets = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return Response(200, {"access_token": "opaque-token"})

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        if url == collect.SEARCH_URL:
            return Response(200, {"itemSummaries": [{
                "itemId": "v1|123456789012|0",
                "title": "Vintage card 1/102",
                "itemWebUrl": "https://www.ebay.com/itm/123456789012",
                "image": {"imageUrl": "https://i.ebayimg.com/images/g/example/s-l225.jpg"},
                "thumbnailImages": [{"imageUrl": "https://i.ebayimg.com/images/g/decoy/s-l225.jpg"}],
                "seller": {"username": "must-not-be-cached"},
            }]})
        if url == "https://i.ebayimg.com/images/g/example/s-l1600.jpg":
            return Response(200, content=photo_bytes(), headers={"content-type": "image/jpeg"})
        raise AssertionError(f"Unexpected request host/path: {url}")


def test_collect_caches_only_needed_listing_fields_and_appends_manifest(tmp_path, monkeypatch, capsys):
    credentials = tmp_path / "ebay.env"
    credentials.write_text("EBAY_CLIENT_ID=client\nEBAY_CLIENT_SECRET=secret-value\n")
    destination = tmp_path / "data" / "photo-corpus"
    args = type("Args", (), {
        "credentials": credentials,
        "destination": destination,
        "query": "pokemon vintage card",
        "bucket": "vintage_wotc_raw",
        "count": 1,
    })()
    client = FakeClient()
    pacer_type = collect.Pacer
    monkeypatch.setattr(collect, "Pacer", lambda: pacer_type(interval=0))

    assert collect.collect(args, client) == 1
    assert (destination / "raw" / "0001.jpg").read_bytes() == photo_bytes()
    with (destination / "manifest.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [{
        "photo": "raw/0001.jpg", "bucket": "vintage_wotc_raw", "source_site": "ebay",
        "page_url": "https://www.ebay.com/itm/123456789012", "title": "Vintage card 1/102", "photo_index": "1",
        "width": "1200", "height": "1600", "long_edge": "1600",
    }]
    cached = json.loads(next((destination / "cache" / "ebay").glob("search-*.json")).read_text())
    assert "seller" not in cached["itemSummaries"][0]
    assert "must-not-be-cached" not in capsys.readouterr().out
    assert "secret-value" not in capsys.readouterr().err
    assert client.closed is False  # Caller-supplied HTTP clients remain caller-owned.


def test_verify_connection_does_not_cache_or_print_credentials(tmp_path, monkeypatch, capsys):
    credentials = tmp_path / "ebay.env"
    credentials.write_text("EBAY_CLIENT_ID=client\nEBAY_CLIENT_SECRET=secret-value\n")
    client = FakeClient()
    monkeypatch.setattr(collect.httpx, "Client", lambda **kwargs: client)
    pacer_type = collect.Pacer
    monkeypatch.setattr(collect, "Pacer", lambda: pacer_type(interval=0))
    monkeypatch.chdir(tmp_path)

    assert collect.verify_connection(credentials, "pokemon card") == 1
    assert list(tmp_path.iterdir()) == [credentials]
    assert "secret-value" not in capsys.readouterr().out
    assert client.closed is True
