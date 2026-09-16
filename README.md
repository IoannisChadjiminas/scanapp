# Scanapp

Visual identification experiment for **English Pokémon cards**. The browser UI captures or uploads a photograph; FastAPI runs DINOv2 Small (ONNX) retrieval with optional RapidOCR reranking. Uploaded photographs are discarded after processing. Model weights are used as published — nothing is trained here.

## Local Docker

```bash
cp .env.example .env
docker compose --profile tools run --build --rm bootstrap
docker compose up --build -d
```

Open [http://localhost:8080](http://localhost:8080).

Later starts: `docker compose up -d`. `docker compose down` keeps catalogue and vector volumes.

Bootstrap is resumable. The first run needs internet access; recognition then uses local artifacts under the `scanapp-data` volume.

Default catalogue import is a few English sets (`base1,sv01,swsh3`). Set `CATALOGUE_SETS=all` in `.env` for the full English catalogue.

## Layout

| Path | Role |
|---|---|
| `app/`, `components/` | Next.js App Router UI (static export) |
| `api/app/` | FastAPI recognition API |
| `api/bootstrap/` | Model export, TCGdex import, embeddings |
| `api/eval/` | Accuracy harness and optional Tesseract comparison |
| `docker/` | API, web, bootstrap images and Caddyfiles |

Runtime containers do not include Node.js, PyTorch, or PaddlePaddle. Bootstrap is the tools image.

## API

- `POST /api/v1/images/prepare` — JPEG preview for HEIC and other uploads the browser cannot show
- `POST /api/v1/scans` — recognize a card
- `GET /api/v1/cards?q=` — catalogue search
- `POST /api/v1/scans/{id}/feedback` — confirm, correct, or reject
- `GET /api/v1/session/results` — anonymous session results
- `GET /api/v1/health` — catalogue and model readiness

Frontend types live in `lib/api-types.ts`. Regenerate the OpenAPI document with:

```bash
PYTHONPATH=api python -c "from app.main import app; import json; print(json.dumps(app.openapi(), indent=2))"
```

## Dokploy public URL

Use `compose.dokploy.yaml` only. Do not deploy `compose.override.yaml` or `compose.prod.yaml`. Attach the domain to service `web`, port `80`. After the first deploy, run bootstrap once so the catalogue volume is filled.

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

Labeled development photographs go in `datasets/` as `images/` plus `labels.jsonl`. After artifacts exist:

```bash
PYTHONPATH=api python -m eval.harness --dataset datasets/dev --preprocess pad --out eval-pad.json
```

Tesseract is only for a 50-image development comparison (`python -m eval.tesseract_compare`). Production OCR is RapidOCR.

The scanner returns the most likely card as `matched`, or `no_match` when visual score or the gap to the next card is too small.
