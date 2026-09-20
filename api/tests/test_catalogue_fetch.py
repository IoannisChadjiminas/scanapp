import httpx
import pytest
from pathlib import Path

from app.db import connect, init_catalog
from bootstrap.catalogue import (
    backfill_missing_tpc_images,
    card_detail_url,
    cdn_image_url,
    fetch_card_detail,
    fill_empty_set_briefs,
    infer_serie_id,
    listing_card_name,
    local_id_cdn_candidates,
    parse_tpc_collector,
    resolve_card_cdn_url,
    stub_card_from_brief,
    tpc_abs_url,
    tpc_list_expansion,
    upsert_card,
)
from bootstrap.download import download_file


def test_card_detail_url_encodes_question_mark() -> None:
    assert card_detail_url("en", "exu-?").endswith("/en/cards/exu-%3F")


def test_fetch_skips_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert fetch_card_detail("exu-?", "en", client=client, retries=1) is None


def test_fetch_retries_then_returns(monkeypatch) -> None:
    monkeypatch.setattr("bootstrap.catalogue.time.sleep", lambda _delay: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"id": "base1-4", "name": "Charizard"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        body = fetch_card_detail("base1-4", "en", client=client)

    assert body == {"id": "base1-4", "name": "Charizard"}
    assert calls["n"] == 3


def test_download_retries_503_then_writes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("bootstrap.download.time.sleep", lambda _delay: None)
    dest = tmp_path / "dp3-87.webp"
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, content=b"webp-bytes")

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        download_file("https://assets.tcgdex.net/en/dp/dp3/87/high.webp", dest, client=client)

    assert dest.read_bytes() == b"webp-bytes"
    assert calls["n"] == 3


def test_download_does_not_retry_404(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("bootstrap.download.time.sleep", lambda _delay: None)
    dest = tmp_path / "missing.webp"
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        with pytest.raises(httpx.HTTPStatusError):
            download_file("https://assets.tcgdex.net/missing.webp", dest, client=client, retries=4)

    assert calls["n"] == 1
    assert not dest.exists()


def test_infer_serie_and_cdn_url() -> None:
    assert infer_serie_id("S8a") == "S"
    assert infer_serie_id("SM1M") == "SM"
    assert infer_serie_id("sv03.5") == "sv"
    assert local_id_cdn_candidates("14") == ["14", "014"]
    assert (
        cdn_image_url("ja", "S", "S8a", "014")
        == "https://assets.tcgdex.net/ja/S/S8a/014/high.webp"
    )
    assert listing_card_name("Cosmog (s8a 014)From 0,02 €") == "Cosmog"


def test_empty_set_briefs_probe_cdn_and_skip_gaps() -> None:
    hits = {str(n).zfill(3) for n in range(1, 26)} | {"029"}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "HEAD":
            local_id = url.rstrip("/").split("/")[-2] if "/high.webp" in url else ""
            if local_id in hits:
                return httpx.Response(200)
            return httpx.Response(404)
        if url.endswith("/ja/sets/S8a"):
            return httpx.Response(
                200,
                json={
                    "id": "S8a",
                    "name": "25th アニバーサリーコレクション",
                    "serie": {"id": "S", "name": "剣と盾"},
                    "cardCount": {"official": 28, "total": 28},
                    "cards": [],
                },
            )
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        briefs = fill_empty_set_briefs(
            client,
            "ja",
            {"S8a"},
            [],
            {},
            quality="high",
        )

    ids = {item["id"] for item in briefs}
    assert "S8a-014" in ids
    assert "S8a-001" in ids
    assert "S8a-025" in ids
    assert "S8a-029" in ids
    assert "S8a-026" not in ids
    assert "S8a-028" not in ids


def test_stub_card_when_detail_404_but_cdn_exists() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "HEAD":
            if url.endswith("/ja/S/S8a/014/high.webp"):
                return httpx.Response(200)
            return httpx.Response(404)
        return httpx.Response(404)

    brief = {
        "id": "S8a-014",
        "localId": "014",
        "set": {
            "id": "S8a",
            "name": "25th アニバーサリーコレクション",
            "serie": {"id": "S"},
        },
    }
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        card = stub_card_from_brief(
            brief, "ja", client=client, sets={}, quality="high"
        )
    assert card is not None
    assert card["id"] == "S8a-014"
    assert card["image"] == "https://assets.tcgdex.net/ja/S/S8a/014"


def test_resolves_cdn_when_api_image_is_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD" and str(request.url).endswith(
            "/ja/SM/SM1M/026/high.webp"
        ):
            return httpx.Response(200)
        return httpx.Response(404)

    card = {
        "id": "SM1M-026",
        "localId": "026",
        "image": None,
        "set": {"id": "SM1M", "serie": {"id": "SM"}},
    }
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        url = resolve_card_cdn_url(client, "ja", card, {}, "high")
    assert url == "https://assets.tcgdex.net/ja/SM/SM1M/026/high.webp"
    assert card["image"] == "https://assets.tcgdex.net/ja/SM/SM1M/026"


def test_parse_tpc_collector_and_abs_url() -> None:
    html = (
        '<img src="/assets/images/card_images/large/SV-P/'
        '044851_E_DABURUDORAGONENERUGI.jpg" />'
        "&nbsp;142&nbsp;/&nbsp;SV-P&nbsp;"
    )
    assert parse_tpc_collector(html) == ("142", "SV-P")
    assert tpc_abs_url("/assets/images/card_images/large/SV-P/x.jpg").endswith(
        "/assets/images/card_images/large/SV-P/x.jpg"
    )


def test_tpc_list_expansion_paginates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page") or "1")
        assert request.url.params.get("pg") == "SV-P"
        assert request.url.params.get("regulation_sidebar_form") == "all"
        cards = [
            {
                "cardID": "44851" if page == 1 else "44852",
                "cardThumbFile": "/assets/images/card_images/large/SV-P/a.jpg",
                "cardNameAltText": "ダブルドラゴンエネルギー",
            }
        ]
        return httpx.Response(
            200,
            json={"result": 1, "maxPage": 2, "cardList": cards},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        cards = tpc_list_expansion(client, "SV-P")
    assert [item["cardID"] for item in cards] == ["44851", "44852"]


def _ja_card(conn, card_id: str, **overrides) -> None:
    fields = {
        "provider_id": card_id.split(":", 1)[-1],
        "name": "ダブルドラゴンエネルギー",
        "set_id": "SV-P",
        "set_name": "SV-P",
        "collector_number": "142",
        "language": "ja",
        "category": None,
        "rarity": None,
        "illustrator": None,
        "variants_json": "{}",
        "image_path": None,
        "has_image": 0,
        "cardmarket_id": None,
        "cardmarket_url": None,
        "cardmarket_verified": 0,
        "cardmarket_provenance": "none",
        "cardmarket_verified_at": None,
        "remote_image_url": None,
    }
    fields.update(overrides)
    upsert_card(conn, card_id=card_id, **fields)


def test_tpc_backfill_downloads_official_image(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("bootstrap.catalogue.time.sleep", lambda _delay: None)
    monkeypatch.setattr("bootstrap.download.time.sleep", lambda _delay: None)
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _ja_card(conn, "ja:SV-P-142")
    _ja_card(
        conn,
        "ja:M-P-040",
        provider_id="M-P-040",
        name="基本闘エネルギー",
        set_id="M-P",
        collector_number="040",
    )
    conn.commit()
    image = (
        "https://www.pokemon-card.com/assets/images/card_images/large/"
        "SV-P/044851_E_DABURUDORAGONENERUGI.jpg"
    )
    energy = (
        "https://www.pokemon-card.com/assets/images/card_images/large/"
        "M-P/048327_E_KIHONTOUENERUGI.jpg"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://www.pokemon-card.com/card-search/resultAPI.php"):
            expansion = request.url.params.get("pg")
            if expansion == "SV-P":
                cards = [
                    {
                        "cardID": "44851",
                        "cardThumbFile": "/assets/images/card_images/large/SV-P/"
                        "044851_E_DABURUDORAGONENERUGI.jpg",
                        "cardNameAltText": "ダブルドラゴンエネルギー",
                    }
                ]
            elif expansion == "M-P":
                cards = [
                    {
                        "cardID": "48327",
                        "cardThumbFile": "/assets/images/card_images/large/M-P/"
                        "048327_E_KIHONTOUENERUGI.jpg",
                        "cardNameAltText": "基本闘エネルギー",
                    }
                ]
            else:
                cards = []
            return httpx.Response(
                200, json={"result": 1, "maxPage": 1, "cardList": cards}
            )
        if url.endswith("/details.php/card/44851"):
            return httpx.Response(
                200,
                text="&nbsp;142&nbsp;/&nbsp;SV-P&nbsp;",
            )
        if url.endswith("/details.php/card/48327"):
            return httpx.Response(
                200,
                text="&nbsp;040&nbsp;/&nbsp;M-P&nbsp;",
            )
        if url == image:
            return httpx.Response(200, content=b"dragon-jpg")
        if url == energy:
            return httpx.Response(200, content=b"energy-jpg")
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        stats = backfill_missing_tpc_images(
            conn, client, tmp_path, languages=["ja"], concurrency=2
        )
    assert stats["found"] == 2
    assert stats["downloaded"] == 2
    dragon = conn.execute("SELECT * FROM cards WHERE id = 'ja:SV-P-142'").fetchone()
    assert dragon["remote_image_url"] == image
    assert dragon["has_image"] == 1
    assert Path(dragon["image_path"]).read_bytes() == b"dragon-jpg"
    fighting = conn.execute("SELECT * FROM cards WHERE id = 'ja:M-P-040'").fetchone()
    assert fighting["remote_image_url"] == energy
    assert Path(fighting["image_path"]).read_bytes() == b"energy-jpg"


def test_tpc_backfill_skips_ambiguous_collector(tmp_path) -> None:
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _ja_card(conn, "ja:SV-P-142", name="ダブルドラゴンエネルギー")
    conn.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "resultAPI.php" in url:
            return httpx.Response(
                200,
                json={
                    "result": 1,
                    "maxPage": 1,
                    "cardList": [
                        {
                            "cardID": "1",
                            "cardThumbFile": "/assets/images/card_images/large/SV-P/a.jpg",
                            "cardNameAltText": "エーフィex",
                        },
                        {
                            "cardID": "2",
                            "cardThumbFile": "/assets/images/card_images/large/SV-P/b.jpg",
                            "cardNameAltText": "ダブルドラゴンエネルギー",
                        },
                    ],
                },
            )
        if url.endswith("/card/1"):
            return httpx.Response(200, text="&nbsp;142&nbsp;/&nbsp;SV-P&nbsp;")
        if url.endswith("/card/2"):
            return httpx.Response(200, text="&nbsp;142&nbsp;/&nbsp;SV-P&nbsp;")
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        stats = backfill_missing_tpc_images(
            conn, client, tmp_path, languages=["ja"], concurrency=2
        )
    # Same collector, unique Japanese name still maps the energy.
    assert stats["found"] == 1
    row = conn.execute("SELECT * FROM cards WHERE id = 'ja:SV-P-142'").fetchone()
def test_tpc_backfill_uses_unique_name_without_details(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("bootstrap.catalogue.time.sleep", lambda _delay: None)
    monkeypatch.setattr("bootstrap.download.time.sleep", lambda _delay: None)
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _ja_card(conn, "ja:SV-P-142")
    conn.commit()
    image = (
        "https://www.pokemon-card.com/assets/images/card_images/large/"
        "SV-P/044851_E_DABURUDORAGONENERUGI.jpg"
    )
    calls = {"details": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "resultAPI.php" in url:
            return httpx.Response(
                200,
                json={
                    "result": 1,
                    "maxPage": 1,
                    "cardList": [
                        {
                            "cardID": "44851",
                            "cardThumbFile": "/assets/images/card_images/large/SV-P/"
                            "044851_E_DABURUDORAGONENERUGI.jpg",
                            "cardNameAltText": "ダブルドラゴンエネルギー",
                        }
                    ],
                },
            )
        if "/details.php/card/" in url:
            calls["details"] += 1
            return httpx.Response(404)
        if url == image:
            return httpx.Response(200, content=b"dragon-jpg")
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        stats = backfill_missing_tpc_images(
            conn, client, tmp_path, languages=["ja"], concurrency=1
        )
    assert calls["details"] == 0
    assert stats["downloaded"] == 1
    row = conn.execute("SELECT * FROM cards WHERE id = 'ja:SV-P-142'").fetchone()
    assert row["remote_image_url"] == image


def test_tpc_get_retries_403(monkeypatch) -> None:
    monkeypatch.setattr("bootstrap.catalogue.time.sleep", lambda _delay: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(403)
        return httpx.Response(200, text="ok")

    from bootstrap.catalogue import tpc_get

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = tpc_get(client, "https://www.pokemon-card.com/card-search/details.php/card/1")
    assert response.text == "ok"
    assert calls["n"] == 3
