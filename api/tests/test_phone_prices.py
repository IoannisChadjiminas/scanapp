import gzip
import hashlib
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import phone_prices
from app.config import Settings
from app.db import connect, init_catalog
from app.price_sources import best_prices, import_guide, refresh_all
from app.routes.card_prices import router

GUIDE = {
    "version": 1,
    "createdAt": "2026-11-20T02:43:56+0100",
    "priceGuides": [
        {"idProduct": 100, "low": 3.5, "trend": 4.2, "avg7": 4.0, "trend-holo": 12.0},
        {"idProduct": 101, "trend": None, "trend-holo": None},
        {"idProduct": 102, "trend": 0, "trend-holo": 2.5},
    ],
}


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _index(root, ids, prints=None):
    """A published phone index whose version file hashes its files."""
    version = hashlib.sha256("\n".join(ids).encode()).hexdigest()
    folder = root / version
    folder.mkdir(parents=True)
    (folder / "card_index.ids.txt").write_text("".join(f"{card}\n" for card in ids))
    (folder / "card_index.f16.bin").write_bytes(b"\0" * 4)
    (folder / "card_index.meta.tsv").write_text("#id\tname\tnumber\tprinted_number\tset_total\tlanguage\n")
    names = ["card_index.f16.bin", "card_index.ids.txt", "card_index.meta.tsv"]
    if prints is not None:
        (folder / "card_index.prints.tsv").write_text(
            "#id\treprint_of\tprinting\tnumber\n" + "".join(f"{card}\t{ids[0]}\tother\t1\n" for card in prints))
        names.append("card_index.prints.tsv")
    files = {name: {"bytes": (folder / name).stat().st_size, "sha256": _digest(folder / name)} for name in names}
    (folder / "card_index.version.json").write_text(json.dumps({"version": version, "files": files}))
    (root / "ACTIVE").write_text(version)
    return version


def _catalog(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    return conn


def _card(conn, card_id, product, variants=None, set_name="Base Set"):
    conn.execute(
        "INSERT INTO cards (id, provider_id, name, set_id, set_name, collector_number, language,"
        " variants_json, cardmarket_id, has_image, image_path) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (card_id, card_id, "Pikachu", "base1", set_name, "58", "en",
         json.dumps(variants or {"normal": True}), product, 1, "/x.webp"),
    )
    conn.commit()


def _settings(tmp_path, **values):
    return Settings(card_index_publish_dir=tmp_path / "index", card_prices_dir=tmp_path / "prices",
                    _env_file=None, **values)


def _rows(path):
    return gzip.decompress(path.read_bytes()).decode().splitlines()


def test_file_has_the_trend_the_app_shows_for_each_index_card(tmp_path):
    conn = _catalog(tmp_path)
    _card(conn, "en:a", 100)
    _card(conn, "en:b", 100, {"normal": False, "reverse": True}, set_name="Jungle\tSet")
    _card(conn, "en:c", 101)
    _card(conn, "en:d", 102)
    _card(conn, "en:not-indexed", 100)
    import_guide(conn, GUIDE)
    _index(tmp_path / "index", ["en:a", "en:b", "en:c", "en:missing"], prints=["en:d"])
    version = phone_prices.build(conn, tmp_path / "index", tmp_path / "prices", guide_date="2026-11-20T01:43:56Z")
    folder = tmp_path / "prices" / version
    assert (tmp_path / "prices" / "ACTIVE").read_text() == version
    assert _digest(folder / phone_prices.FILE_NAME) == version
    lines = _rows(folder / phone_prices.FILE_NAME)
    assert lines[0] == phone_prices.HEADER.rstrip("\n")
    rows = {line.split("\t")[0]: line.split("\t") for line in lines[1:]}
    # Same trend as best_prices' price file figures; the reverse-only card reads -holo.
    assert {p["label"]: p["amount"] for p in best_prices(conn, "en:a", None)}["Trend"] == 4.2
    assert rows["en:a"][1:3] == ["420", "Base Set"]
    assert rows["en:b"][1:3] == ["1200", "Jungle Set"]
    assert rows["en:c"][1] == ""  # No trend: set name only.
    assert rows["en:d"][1] == "250"  # A printing from the prints file.
    assert rows["en:a"][3] == "/api/v1/cards/en:a/image"
    assert "en:not-indexed" not in rows and "en:missing" not in rows
    meta = json.loads((folder / "manifest.json").read_text())
    assert meta["rows"] == 4 and meta["priced"] == 3 and meta["guide_date"] == "2026-11-20T01:43:56Z"


def test_same_data_gives_the_same_version_and_old_versions_are_pruned(tmp_path):
    conn = _catalog(tmp_path)
    _card(conn, "en:a", 100)
    import_guide(conn, GUIDE)
    _index(tmp_path / "index", ["en:a"])
    first = phone_prices.build(conn, tmp_path / "index", tmp_path / "prices")
    assert phone_prices.build(conn, tmp_path / "index", tmp_path / "prices") == first
    versions = [first]
    for trend in (5.0, 6.0, 7.0):
        conn.execute("UPDATE cardmarket_guide SET trend = ?", (trend,))
        conn.commit()
        versions.append(phone_prices.build(conn, tmp_path / "index", tmp_path / "prices"))
    kept = {path.name for path in (tmp_path / "prices").iterdir() if path.is_dir()}
    assert kept == set(versions[-1 - phone_prices.KEEP_OLD:])


def test_a_broken_index_keeps_the_previous_file(tmp_path):
    conn = _catalog(tmp_path)
    _card(conn, "en:a", 100)
    import_guide(conn, GUIDE)
    version = _index(tmp_path / "index", ["en:a"])
    settings = _settings(tmp_path)
    first = phone_prices.refresh(conn, settings)
    (tmp_path / "index" / version / "card_index.ids.txt").write_text("en:a\nen:b\n")
    assert phone_prices.refresh(conn, settings) is None
    assert (tmp_path / "prices" / "ACTIVE").read_text() == first


def test_nightly_pass_rebuilds_after_the_guide_import(tmp_path, monkeypatch):
    conn = _catalog(tmp_path)
    _card(conn, "en:a", 100)
    _index(tmp_path / "index", ["en:a"])
    monkeypatch.setattr("app.price_sources.refresh_guide", lambda c, s, h=None: import_guide(c, GUIDE))
    settings = _settings(tmp_path, tcgdex_prices_enabled=False)
    monkeypatch.setattr("app.set_totals.refresh_set_totals", lambda *a, **k: None)
    monkeypatch.setattr("app.set_totals.refresh_set_releases", lambda *a, **k: None)
    refresh_all(conn, settings)
    folder, meta = phone_prices.read_active(tmp_path / "prices")
    assert meta["priced"] == 1
    assert _rows(folder / phone_prices.FILE_NAME)[1].split("\t")[1] == "420"


def _client(settings):
    app = FastAPI()
    app.state.settings = settings
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def test_manifest_and_file_routes(tmp_path):
    conn = _catalog(tmp_path)
    _card(conn, "en:a", 100)
    import_guide(conn, GUIDE)
    _index(tmp_path / "index", ["en:a"])
    settings = _settings(tmp_path)
    client = _client(settings)
    assert client.get("/api/v1/card-prices/manifest").status_code == 404  # Not built yet.
    version = phone_prices.refresh(conn, settings)
    reply = client.get("/api/v1/card-prices/manifest")
    assert reply.status_code == 200 and reply.headers["cache-control"] == "no-cache"
    body = reply.json()
    assert body["version"] == version and body["rows"] == 1 and body["priced"] == 1
    assert body["file"]["url"] == f"card-prices/files/{version}/{phone_prices.FILE_NAME}"
    data = client.get("/api/v1/" + body["file"]["url"])
    assert data.status_code == 200 and "immutable" in data.headers["cache-control"]
    assert hashlib.sha256(data.content).hexdigest() == body["file"]["sha256"] == version
    assert len(data.content) == body["file"]["bytes"]
    etag = data.headers["etag"]
    assert client.get("/api/v1/" + body["file"]["url"], headers={"If-None-Match": etag}).status_code == 304
    assert client.get(f"/api/v1/card-prices/files/{version}/other.txt").status_code == 404
    assert client.get(f"/api/v1/card-prices/files/{'0' * 64}/{phone_prices.FILE_NAME}").status_code == 404
    assert client.get(f"/api/v1/card-prices/files/..%2F/{phone_prices.FILE_NAME}").status_code == 404


def test_routes_are_off_when_publishing_is_off(tmp_path):
    client = _client(_settings(tmp_path, card_prices_publish=False))
    assert client.get("/api/v1/card-prices/manifest").status_code == 404
