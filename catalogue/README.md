# Catalogue builder (not the Scanapp app)

Downloads TCGdex scans, builds DINOv2 vectors, stores CDN image URLs, copies extra-card photos, and packs a staging bundle. Run this **once**, then again only when you add a set or extra.

The live app (`docker compose up`) never does this. Cardmarket **price fetch** stays in the Chrome helper. Product **URLs** are written locally by this tool (from helper maps and set-page dumps on the shared `scanapp-data` volume), then shipped with `./scripts/offload-local.sh`.

## First catalogue (or full rebuild)

```bash
docker compose -f compose.catalogue.yaml run --rm --build catalogue -m bootstrap
```

That downloads models, the default small English sets (`base1`, `sv01`, `swsh3`), extras, and embeddings. Use it on an empty volume, or when you intend to rebuild everything.

## All sets (English, Japanese, Chinese)

Hours of download + embedding, and a lot of local disk for the webps used to build vectors. Japanese and Traditional/Simplified Chinese use different TCGdex set IDs than English; `--sets all` walks every set in each language.

Keep the catalogue you already have (151, extras, helper maps) and add every other set, then match stored Cardmarket URLs and push staging:

```bash
./scripts/catalogue-all.sh
```

Pack without SSH: `./scripts/catalogue-all.sh --local-only`.

Wipe and rebuild from scratch (re-imports extras afterwards):

```bash
CATALOGUE_SETS=all TCGDEX_LANGUAGES=en,ja,zh-cn,zh-tw \
  docker compose -f compose.catalogue.yaml run --rm --build catalogue -m bootstrap
docker compose restart api
```

## Add one set later

English 151 is `sv03.5`. Japanese/Chinese IDs are different; pass the TCGdex id for that language, or use `--sets all` again.

```bash
./scripts/catalogue-add-set.sh sv03.5
docker compose restart api
```

## 151 (local download through staging)

```bash
./scripts/catalogue-151.sh
```

Downloads English 151, waits for Chrome helper Import/Save on local `http://localhost:8080`, writes Cardmarket URLs, packs the tar, copies it to `auctaro-staging`, applies it, and restarts the staging API.

151 already downloaded and imported locally:

```bash
./scripts/catalogue-151.sh --link-offload
```

Download only, or pack without SSH:

```bash
./scripts/catalogue-151.sh --download-only
./scripts/catalogue-151.sh --local-only
```

## Cardmarket URLs (local, then offload)

Point the Chrome helper at the **local** API (`http://localhost:8080`). Import a set page or Save a product URL. That writes into the same Docker volume this builder uses.

After the cards for that set exist locally:

```bash
docker compose -f compose.catalogue.yaml run --rm catalogue -m bootstrap.link
```

That writes verified Singles URLs onto catalogue cards when the name + collector number is unique. Set-page dumps, `cardmarket-maps.json`, and those URLs then go to staging with:

```bash
./scripts/offload-local.sh
```

A catalogue/extra build already runs this link step. Auto-link still cannot invent a URL; `151` slugs like `mew11` vs collector `001` stay unmatched until you Save the product page.

## Extra-card photos only

Add files under `extra-cards/`, then:

```bash
docker compose -f compose.catalogue.yaml run --rm -e BOOTSTRAP_EXTRAS_ONLY=true catalogue \
  -m bootstrap
docker compose restart api
```

## Offload to staging

```bash
./scripts/offload-local.sh
```

Then copy `exports/scanapp-index.tar` to the server and apply (see the script output). Official set webps are not in the tar; thumbnails use TCGdex URLs. Extra-card photos, Cardmarket maps, and stored set-list URLs are included.

End-to-end from this machine (SSH host `auctaro-staging`):

```bash
./scripts/offload-to-staging.sh
```

On the server only, after the tar is in `exports/`:

```bash
./scripts/offload-apply.sh
```
