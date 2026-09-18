# Extra reference cards

Drop a JPEG/WebP here and add a row to `manifest.json`. The catalogue builder copies them into the data volume and rebuilds embeddings.

Each extra image is 1-to-1 with a Cardmarket product: set `cardmarket_url`, or `cardmarket_expansion` + `cardmarket_set_code` (builds `/Singles/{expansion}/{Name}-{CODE}{number}`). Do not guess from the display set name alone.

```bash
docker compose -f compose.catalogue.yaml run --rm -e BOOTSTRAP_EXTRAS_ONLY=true catalogue \
  -m bootstrap
docker compose restart api
```
