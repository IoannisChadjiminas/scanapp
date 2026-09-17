# Extra reference cards

Drop a JPEG/WebP here and add a row to `manifest.json`. Bootstrap copies them into the catalogue volume and rebuilds embeddings.

Each extra image is 1-to-1 with a Cardmarket product: set `cardmarket_url`, or `cardmarket_expansion` + `cardmarket_set_code` (builds `/Singles/{expansion}/{Name}-{CODE}{number}`). Do not guess from the display set name alone.

`BOOTSTRAP_EXTRAS_ONLY=true docker compose --profile tools run --rm bootstrap` imports extras without re-downloading TCGdex.
