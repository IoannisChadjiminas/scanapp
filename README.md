# Scanapp

Visual identification experiment for **English Pokémon cards**. The browser UI captures or uploads a photograph; FastAPI runs DINOv2 Small (ONNX) retrieval with optional RapidOCR reranking. Each scan keeps the upload, the image used for retrieval, and the ranking result under `datasets/review/` so failures can be inspected. Model weights are used as published — nothing is trained here.

## Local Docker

```bash
cp .env.example .env
docker compose up --build -d
```

Open [http://localhost:8080](http://localhost:8080).

Catalogue download, embeddings, and extra-card import are **not** part of this app. They live in `catalogue/` and run separately (`compose.catalogue.yaml`), once per new set. See `catalogue/README.md`.

Later starts: `docker compose up -d`. `docker compose down` keeps catalogue and vector volumes.

## Layout

| Path | Role |
|---|---|
| `app/`, `components/` | Next.js App Router UI (static export) |
| `api/app/` | FastAPI recognition API |
| `catalogue/` | One-off set download, vectors, TCGdex URLs, extra photos, offload |
| `api/eval/` | Accuracy harness and optional Tesseract comparison |
| `datasets/review/` | Saved scan photos, sidecars, and `SUMMARY.md` for failure review |
| `docker/` | API and web images, Caddyfiles |
| `extension/` | Chrome helper: reads Cardmarket listings into the local API |

Runtime containers do not include Node.js, PyTorch, or PaddlePaddle. Those are only in the catalogue builder image.

## API

- `POST /api/v1/images/prepare` — JPEG preview for HEIC and other uploads the browser cannot show
- `POST /api/v1/scans` — recognize a card
- `GET /api/v1/cards?q=` — catalogue search
- `POST /api/v1/scans/{id}/feedback` — confirm, correct, or reject
- `GET /api/v1/session/results` — anonymous session results
- `GET /api/v1/health` — catalogue and model readiness
- `GET /api/v1/review` — saved scan photos and rankings (`needs_attention`, `status`, `limit`, `offset`)
- `GET /api/v1/review/summary` — markdown failure list
- `GET /api/v1/review/cases/{id}` — one scan sidecar
- `GET /api/v1/review/images/{id}.query.jpg` — image the model scored
- `GET /api/v1/review/labels` — confirmed/rejected eval labels
- `POST /api/v1/cardmarket/jobs` — queue a product page for the PC Chrome helper
- `GET /api/v1/cardmarket/prices?url=` — stored listings plus helper/job status
- `POST /api/v1/cardmarket/helper/claim` — helper claims or recovers one job
- `POST /api/v1/cardmarket/helper/renew` — extend the active claim
- `POST /api/v1/cardmarket/helper/complete` — save a sample of listings (idempotent by submission id)
- `POST /api/v1/cardmarket/helper/fail` — retry with backoff or fail the job
- `POST /api/v1/cardmarket/helper/release` — return a claim without burning an attempt
- `POST /api/v1/cardmarket/helper/status` — helper heartbeat and queue counts

Helper write routes require `Authorization: Bearer <token>` from `python -m app.helper_credential`. Review routes accept the same helper token, or `REVIEW_TOKEN` (`Authorization: Bearer` or `X-Review-Token`). Frontend types live in `lib/api-types.ts`. The PC Chrome helper lives in `extension/` (`extension/README.md`). A confident match or confirmation queues the product; the helper reads listings in one background tab.

PC extension and CDP helper price reads are temporarily disabled by default
(`CARDMARKET_HELPER_ENABLED=false`). The API advertises them as unavailable,
does not hand them jobs, and rejects renewals and price submissions. Stored
prices, phone reads, and the separately configured paid scraper remain available.
To restore PC reads, set `CARDMARKET_HELPER_ENABLED=true` in the API environment
and restart/redeploy the API. No Flutter rebuild is needed.

Regenerate the OpenAPI document with:

```bash
PYTHONPATH=api python -c "from app.main import app; import json; print(json.dumps(app.openapi(), indent=2))"
```

## Dokploy public URL

Use `compose.dokploy.yaml` only. Do not deploy `compose.override.yaml` or `compose.prod.yaml`. Attach the domain to service `web`, port `80`. Fill the catalogue volume from a local builder run (`./scripts/offload-local.sh`); see `catalogue/README.md`.

`npm run dev` only serves the UI on [http://localhost:3000](http://localhost:3000). It does not start FastAPI. Without the API you will see **Recognition API is not running**.

Use Docker for the full stack (`http://localhost:8080`), or run the API yourself and point the UI at it:

```bash
npm install
NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev
```

The production path is the static export behind Caddy, which proxies `/api/v1` to FastAPI. Interactive camera and crop UI are Client Components; the page shell is a Server Component.

## Phone camera testing

Browsers require a secure context for `getUserMedia`. `localhost` works on the computer. A plain `http://LAN-IP` URL from a phone does not.

Local Compose publishes HTTPS on port `8443` with Caddy’s internal CA (`docker/Caddyfile.local`). On the phone, install and trust that certificate, then open `https://<computer-lan-ip>:8443`.

## Production

```bash
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

Set `PUBLIC_HOST` to the public hostname. Caddy terminates HTTPS. The API is not published directly. Target runtime is one FastAPI worker on a 2 GiB Droplet; scans are serialized (one active, two waiting, then `503`).

## Evaluation

Python unit tests (no models required):

```bash
pip install -r api/requirements.txt -r api/requirements-dev.txt
pytest -c api/pytest.ini
```

Labeled development photographs go in `datasets/` as `images/` plus `labels.jsonl`. Live scans also write `datasets/review/` (`SUMMARY.md`, query JPEGs, and confirmed `labels.jsonl`). After artifacts exist:

```bash
PYTHONPATH=api python -m eval.harness --dataset datasets/review --preprocess pad --out eval-pad.json
```

Tesseract is only for a 50-image development comparison (`python -m eval.tesseract_compare`). Production OCR is RapidOCR.

The scanner returns the most likely card as `matched`, or `no_match` when visual score or the gap to the next card is too small.
