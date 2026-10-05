"""Staging-only negative feedback test, using an isolated HTTP session."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    args = parser.parse_args()
    with httpx.Client(base_url="https://staging-scan.auctaro.com/api/v1/",
                      timeout=60) as client:
        client.get("session/results").raise_for_status()
        scan = client.post("scans", data={"language": "ja"},
                           files={"image": ("card.jpg", args.image.read_bytes(), "image/jpeg")})
        scan.raise_for_status()
        result = scan.json()
        top = result["suggestions"][0]
        assert top["card_id"] == "ja:SV-P-051"
        assert not any("Victini" in v["url"] for v in top["cardmarket_variants"])
        feedback = client.post(f"scans/{result['id']}/feedback", json={
            "action": "confirm", "card_id": "ja:SV-P-051",
            "cardmarket_url": "https://www.cardmarket.com/en/Pokemon/Products/Singles/Scarlet-Violet-Promos/Victini-ex-V1-SV-P051",
        })
        assert feedback.status_code == 409, feedback.status_code
        history = client.get("session/results")
        history.raise_for_status()
        saved = next(r for r in history.json()["results"] if r["scan_id"] == result["id"])
        assert saved["confirmed_card_id"] is None
        assert saved["chosen_cardmarket_url"] is None
        print(json.dumps({"base_id": top["card_id"], "bad_variant_offered": False,
                          "wrong_listing_http_status": feedback.status_code,
                          "wrong_listing_saved": False}))


if __name__ == "__main__":
    main()
