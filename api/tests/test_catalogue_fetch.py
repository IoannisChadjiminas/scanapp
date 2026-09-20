import httpx
import pytest

from bootstrap.catalogue import card_detail_url, fetch_card_detail
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
