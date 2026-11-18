from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.card_image_mirror import (
    CACHE_CONTROL,
    CardImageCdn,
    DryRunStore,
    cdn_image_url,
    is_local_source,
    load_card_image_cdn,
    local_object_base,
    mirror_card_images,
    mirror_object_base,
    open_registry,
)
from app.card_images import display_image_url
from app.db import connect, init_catalog
from bootstrap.catalogue import upsert_card

WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 16
TCGDEX = "https://assets.tcgdex.net/en/sv/sv03.5/001/high.webp"
CDN = "https://img.example"


def _card(conn, card_id: str, **overrides) -> None:
    fields = {
        "provider_id": card_id.split(":", 1)[-1],
        "name": "Pikachu",
        "set_id": "sv03.5",
        "set_name": "151",
        "collector_number": "001",
        "language": "en",
        "category": None,
        "rarity": None,
        "illustrator": None,
        "variants_json": "{}",
        "image_path": None,
        "has_image": 0,
        "cardmarket_id": None,
        "cardmarket_url": None,
        "cardmarket_verified": 0,
        "cardmarket_provenance": None,
        "cardmarket_verified_at": None,
        "remote_image_url": None,
    }
    fields.update(overrides)
    upsert_card(conn, card_id=card_id, **fields)


def _settings(tmp_path: Path, base_url: str = CDN) -> SimpleNamespace:
    return SimpleNamespace(
        card_image_cdn_base_url=base_url,
        card_image_mirror_sqlite=tmp_path / "card-image-mirror.sqlite",
    )


class RecordingStore:
    def __init__(self, fail_keys: set[str] | None = None) -> None:
        self.puts: list[dict] = []
        self.fail_keys = fail_keys or set()

    def put_object(self, **kwargs) -> None:
        if kwargs["Key"] in self.fail_keys:
            raise OSError("upload refused")
        self.puts.append(kwargs)


def test_object_base_is_derived_only_from_tcgdex_art() -> None:
    assert mirror_object_base(TCGDEX) == "en/sv/sv03.5/001"
    assert mirror_object_base("https://assets.tcgdex.net/ja/sv/sv1/001/low.webp") == "ja/sv/sv1/001"
    assert mirror_object_base("https://product-images.s3.cardmarket.com/51/BS/273753/273753.jpg") is None
    assert mirror_object_base("http://assets.tcgdex.net/en/sv/sv03.5/001/high.webp") is None
    assert mirror_object_base("https://assets.tcgdex.net/en/sv/../001/high.webp") is None
    assert mirror_object_base("https://assets.tcgdex.net/high.webp") is None
    assert mirror_object_base(None) is None
    assert cdn_image_url(CDN + "/", "en/sv/sv03.5/001", "low") == f"{CDN}/en/sv/sv03.5/001/low.webp"


def test_display_url_prefers_mirrored_art_and_falls_back_otherwise(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    registry = open_registry(settings.card_image_mirror_sqlite)
    registry.execute("INSERT INTO mirrored_images VALUES ('en:sv03.5-001', 'en/sv/sv03.5/001', 'x', 'now')")
    registry.execute("INSERT INTO mirrored_images VALUES ('en:moved', 'en/old/base/009', 'x', 'now')")
    registry.commit()
    registry.close()
    catalog = SimpleNamespace(card_image_cdn=load_card_image_cdn(settings))

    mirrored = {"id": "en:sv03.5-001", "remote_image_url": TCGDEX}
    assert display_image_url(mirrored, catalog) == f"{CDN}/en/sv/sv03.5/001/high.webp"
    # Not mirrored yet: the live TCGdex file.
    assert display_image_url({"id": "en:other", "remote_image_url": TCGDEX}, catalog) == TCGDEX
    # Mirrored from a path the catalogue no longer uses: the copy is stale.
    moved = {"id": "en:moved", "remote_image_url": TCGDEX}
    assert display_image_url(moved, catalog) == TCGDEX
    # No CDN configured: unchanged behaviour.
    assert display_image_url(mirrored, SimpleNamespace()) == TCGDEX
    assert display_image_url(mirrored) == TCGDEX
    assert load_card_image_cdn(_settings(tmp_path, base_url="")) is None


def test_cdn_disabled_for_non_https_base(tmp_path: Path) -> None:
    cdn = CardImageCdn("http://img.example", tmp_path / "missing.sqlite")
    assert not cdn.enabled
    assert cdn.url_for("en:x", TCGDEX) is None


def test_mirror_uploads_both_qualities_and_is_resumable(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    catalog = connect(tmp_path / "catalog.sqlite")
    init_catalog(catalog)
    local = tmp_path / "reference-images" / "en" / "sv03.5-001.webp"
    local.parent.mkdir(parents=True)
    local.write_bytes(WEBP + b"local-high")
    _card(catalog, "en:sv03.5-001", image_path=str(local), has_image=1, remote_image_url=TCGDEX)
    _card(catalog, "en:sv03.5-002", remote_image_url="https://assets.tcgdex.net/en/sv/sv03.5/002/high.webp")
    _card(catalog, "ja:sv1-001", language="ja", remote_image_url="https://assets.tcgdex.net/ja/sv/sv1/001/high.webp")
    _card(catalog, "en:cardmarket", remote_image_url="https://product-images.s3.cardmarket.com/1/2/3/3.jpg")
    _card(catalog, "en:local-only", image_path=str(local), has_image=1)

    fetched: list[str] = []

    def fetch(url: str) -> bytes:
        fetched.append(url)
        return WEBP + url.encode()

    store = RecordingStore()
    report = mirror_card_images(catalog, settings, store=store, bucket="art", fetch=fetch, language="en")
    assert report.as_dict() == {"candidates": 2, "uploaded": 2, "already_mirrored": 0, "failed": 0}
    keys = [put["Key"] for put in store.puts]
    assert keys == [
        "en/sv/sv03.5/001/high.webp",
        "en/sv/sv03.5/001/low.webp",
        "en/sv/sv03.5/002/high.webp",
        "en/sv/sv03.5/002/low.webp",
    ]
    # The bootstrap's reference file stands in for TCGdex's high.webp.
    assert store.puts[0]["Body"] == WEBP + b"local-high"
    assert "https://assets.tcgdex.net/en/sv/sv03.5/001/high.webp" not in fetched
    assert "https://assets.tcgdex.net/en/sv/sv03.5/001/low.webp" in fetched
    assert "https://assets.tcgdex.net/en/sv/sv03.5/002/high.webp" in fetched
    assert all(put["Bucket"] == "art" for put in store.puts)
    assert all(put["ContentType"] == "image/webp" for put in store.puts)
    assert all(put["CacheControl"] == CACHE_CONTROL for put in store.puts)

    # A second run uploads nothing for recorded cards; the other language is new.
    again = RecordingStore()
    report = mirror_card_images(catalog, settings, store=again, bucket="art", fetch=fetch)
    assert report.as_dict() == {"candidates": 1, "uploaded": 1, "already_mirrored": 2, "failed": 0}
    assert [put["Key"] for put in again.puts] == ["ja/sv/sv1/001/high.webp", "ja/sv/sv1/001/low.webp"]

    with sqlite3.connect(settings.card_image_mirror_sqlite) as registry:
        rows = registry.execute("SELECT card_id, object_base FROM mirrored_images ORDER BY card_id").fetchall()
    assert rows == [
        ("en:sv03.5-001", "en/sv/sv03.5/001"),
        ("en:sv03.5-002", "en/sv/sv03.5/002"),
        ("ja:sv1-001", "ja/sv/sv1/001"),
    ]


def test_mirror_records_a_card_only_after_both_uploads(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    catalog = connect(tmp_path / "catalog.sqlite")
    init_catalog(catalog)
    _card(catalog, "en:sv03.5-001", remote_image_url=TCGDEX)
    _card(catalog, "en:sv03.5-002", remote_image_url="https://assets.tcgdex.net/en/sv/sv03.5/002/high.webp")

    def fetch(url: str) -> bytes:
        if url.endswith("/002/low.webp"):
            return b"<html>rate limited</html>"
        return WEBP + url.encode()

    store = RecordingStore(fail_keys={"en/sv/sv03.5/001/low.webp"})
    messages: list[str] = []
    report = mirror_card_images(catalog, settings, store=store, bucket="art", fetch=fetch, log=messages.append)
    assert report.as_dict() == {"candidates": 2, "uploaded": 0, "already_mirrored": 0, "failed": 2}
    assert messages == ["skip en:sv03.5-001: OSError", "skip en:sv03.5-002: ValueError"]
    # Nothing that is not a WebP file reaches the bucket.
    assert all(put["Body"].startswith(b"RIFF") for put in store.puts)
    with sqlite3.connect(settings.card_image_mirror_sqlite) as registry:
        assert registry.execute("SELECT count(*) FROM mirrored_images").fetchone()[0] == 0


def test_mirror_limit_and_dry_run(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    catalog = connect(tmp_path / "catalog.sqlite")
    init_catalog(catalog)
    for number in ("001", "002", "003"):
        _card(catalog, f"en:sv03.5-{number}", remote_image_url=f"https://assets.tcgdex.net/en/sv/sv03.5/{number}/high.webp")
    store = DryRunStore()
    report = mirror_card_images(catalog, settings, store=store, bucket="x", fetch=lambda url: WEBP, limit=2)
    assert report.uploaded == 2 and report.candidates == 2
    assert len(store.keys) == 4


def test_dry_run_records_nothing_so_a_real_run_still_sees_every_card(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    catalog = connect(tmp_path / "catalog.sqlite")
    init_catalog(catalog)
    for number in ("001", "002"):
        _card(catalog, f"en:sv03.5-{number}", remote_image_url=f"https://assets.tcgdex.net/en/sv/sv03.5/{number}/high.webp")

    dry = mirror_card_images(catalog, settings, store=DryRunStore(), bucket="x", fetch=lambda url: WEBP, record=False)
    assert dry.candidates == 2 and dry.already_mirrored == 0
    registry = sqlite3.connect(settings.card_image_mirror_sqlite)
    assert registry.execute("SELECT COUNT(*) FROM mirrored_images").fetchone()[0] == 0
    registry.close()

    again = mirror_card_images(catalog, settings, store=DryRunStore(), bucket="x", fetch=lambda url: WEBP, record=False)
    assert again.candidates == 2 and again.already_mirrored == 0

    real = RecordingStore()
    report = mirror_card_images(catalog, settings, store=real, bucket="x", fetch=lambda url: WEBP)
    assert report.uploaded == 2 and report.already_mirrored == 0


def test_running_api_picks_up_a_mirror_run_without_restart(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    now = [0.0]
    cdn = CardImageCdn(CDN, settings.card_image_mirror_sqlite, clock=lambda: now[0])
    assert cdn.url_for("en:sv03.5-001", TCGDEX) is None

    catalog = connect(tmp_path / "catalog.sqlite")
    init_catalog(catalog)
    _card(catalog, "en:sv03.5-001", remote_image_url=TCGDEX)
    mirror_card_images(catalog, settings, store=RecordingStore(), bucket="art", fetch=lambda url: WEBP)

    # Within the reload window the old answer stands; afterwards the file is re-read.
    assert cdn.url_for("en:sv03.5-001", TCGDEX) is None
    now[0] += 61
    assert cdn.url_for("en:sv03.5-001", TCGDEX) == f"{CDN}/en/sv/sv03.5/001/high.webp"
    assert cdn.url_for("en:sv03.5-001", TCGDEX.replace("high", "low")) == f"{CDN}/en/sv/sv03.5/001/low.webp"
    assert len(cdn) == 1


@pytest.mark.parametrize("quality", ["high", "low"])
def test_tcgdex_quality_is_preserved(quality: str) -> None:
    assert mirror_object_base(f"https://assets.tcgdex.net/en/sv/sv03.5/001/{quality}.webp") == "en/sv/sv03.5/001"


TCGCOLLECTOR = "https://static.tcgcollector.com/content/images/d9/30/d6/d930.webp"


def _jpeg(path: Path, size: tuple[int, int] = (750, 1048)) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (120, 60, 160)).save(path, "JPEG")
    return path


def test_local_object_base_follows_the_stored_copy() -> None:
    base = local_object_base("ja:web1-047", "/data/reference-images/ja/ja_web1-047.jpg")
    assert base.startswith("local/ja/web1-047-") and len(base.rsplit("-", 1)[-1]) == 12
    assert local_object_base("ja:web1-047", "/data/other.jpg") != base
    assert local_object_base("en:exu-%3F", "/x.jpg").startswith("local/en/exu-_3F-")
    assert local_object_base("ja:x", "") is None and local_object_base("", "/x.jpg") is None
    assert is_local_source(TCGCOLLECTOR)
    assert not is_local_source("https://www.pokemon-card.com/a.jpg")
    assert not is_local_source("https://product-images.s3.cardmarket.com/51/1/1.jpg")


def test_display_url_prefers_own_copy_over_third_party_hotlinks(tmp_path: Path) -> None:
    path = "/data/reference-images/ja/ja_web1-047.jpg"
    row = {"id": "ja:web1-047", "remote_image_url": TCGCOLLECTOR, "has_image": 1, "image_path": path}
    # No CDN: the API's own image route, not the dead hotlink.
    assert display_image_url(row) == "/api/v1/cards/ja:web1-047/image"
    other = {**row, "remote_image_url": "https://www.pokemon-card.com/assets/a.jpg"}
    assert display_image_url(other) == "/api/v1/cards/ja:web1-047/image"
    # Cardmarket photos and rows without an own copy keep their address.
    cardmarket = {**row, "remote_image_url": "https://product-images.s3.cardmarket.com/51/1/1.jpg"}
    assert display_image_url(cardmarket) == cardmarket["remote_image_url"]
    assert display_image_url({**row, "has_image": 0}) == TCGCOLLECTOR
    assert display_image_url({**row, "remote_image_url": None}) == "/api/v1/cards/ja:web1-047/image"

    settings = _settings(tmp_path)
    registry = open_registry(settings.card_image_mirror_sqlite)
    base = local_object_base("ja:web1-047", path)
    registry.execute("INSERT INTO mirrored_images VALUES ('ja:web1-047', ?, 'x', 'now')", (base,))
    registry.commit()
    registry.close()
    catalog = SimpleNamespace(card_image_cdn=load_card_image_cdn(settings))
    assert display_image_url(row, catalog) == f"{CDN}/{base}/high.webp"
    # The catalogue now stores another copy: the CDN copy is stale, the route serves the new one.
    moved = {**row, "image_path": "/data/reference-images/ja/new.jpg"}
    assert display_image_url(moved, catalog) == "/api/v1/cards/ja:web1-047/image"
    # The card gained TCGdex art: TCGdex wins, the local copy is not used.
    assert display_image_url({**row, "remote_image_url": TCGDEX}, catalog) == TCGDEX


def test_mirror_converts_allow_listed_copies_and_skips_the_rest(tmp_path: Path) -> None:
    from PIL import Image

    settings = _settings(tmp_path)
    catalog = connect(tmp_path / "catalog.sqlite")
    init_catalog(catalog)
    jpg = _jpeg(tmp_path / "reference-images" / "ja" / "ja_web1-047.jpg")
    _card(catalog, "ja:web1-047", language="ja", image_path=str(jpg), has_image=1, remote_image_url=TCGCOLLECTOR)
    _card(catalog, "ja:M-P-101", language="ja", image_path=str(jpg), has_image=1,
          remote_image_url="https://www.pokemon-card.com/assets/a.jpg")
    _card(catalog, "en:cm", image_path=str(jpg), has_image=1,
          remote_image_url="https://product-images.s3.cardmarket.com/51/1/1.jpg")
    _card(catalog, "ja:no-copy", language="ja", remote_image_url=TCGCOLLECTOR)
    _card(catalog, "ja:missing", language="ja", image_path=str(tmp_path / "gone.jpg"), has_image=1,
          remote_image_url=TCGCOLLECTOR)
    _card(catalog, "en:sv03.5-001", remote_image_url=TCGDEX)

    def fetch(url: str) -> bytes:
        assert "tcgcollector" not in url  # a stored copy is never downloaded again
        return WEBP + url.encode()

    store = RecordingStore()
    messages: list[str] = []
    report = mirror_card_images(catalog, settings, store=store, bucket="art", fetch=fetch,
                                kinds=("local",), log=messages.append)
    assert report.as_dict() == {"candidates": 2, "uploaded": 1, "already_mirrored": 0, "failed": 1}
    assert "skip ja:missing: FileNotFoundError" in messages
    base = local_object_base("ja:web1-047", str(jpg))
    assert [put["Key"] for put in store.puts] == [f"{base}/high.webp", f"{base}/low.webp"]
    assert all(put["ContentType"] == "image/webp" and put["CacheControl"] == CACHE_CONTROL for put in store.puts)
    import io
    with Image.open(io.BytesIO(store.puts[0]["Body"])) as high, Image.open(io.BytesIO(store.puts[1]["Body"])) as low:
        assert high.format == low.format == "WEBP"
        assert high.width == 750 and low.width == 245

    # Resumable, and TCGdex art is handled separately.
    again = mirror_card_images(catalog, settings, store=RecordingStore(), bucket="art", fetch=fetch, kinds=("local",))
    assert again.already_mirrored == 1 and again.uploaded == 0
    tcgdex = mirror_card_images(catalog, settings, store=RecordingStore(), bucket="art", fetch=fetch, kinds=("tcgdex",))
    assert tcgdex.uploaded == 1


def test_cardmarket_photo_is_refused_even_if_listed() -> None:
    from app import card_image_mirror

    row = {"remote_image_url": "https://product-images.s3.cardmarket.com/51/1/1.jpg", "image_path": "/x.jpg"}
    with pytest.raises(ValueError):
        card_image_mirror._mirror_local(row, "local/en/x", store=RecordingStore(), bucket="art")
