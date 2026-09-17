# Recognition review captures

Local Docker bind-mounts this directory to `/data/review` inside the API.

After a scan, open **`SUMMARY.md` first**. It lists cases that need attention and the image paths to inspect.

## Layout

| Path | Role |
|---|---|
| `SUMMARY.md` | Latest failure/confirm summary for review |
| `index.json` | Counts and newest scan ids |
| `review.jsonl` | One JSON object per scan |
| `labels.jsonl` | Eval harness labels (confirmed prints + rejected unknowns) |
| `cases/<scan_id>.json` | Full sidecar: OCR, top-20, timings, versions, feedback |
| `images/<scan_id>.input.jpg` | Upload after crop/rotation, before card detect |
| `images/<scan_id>.query.jpg` | Image that was embedded and ranked |

Photos are gitignored. They stay on disk for local review.

## How to use a case

1. Read `SUMMARY.md` and pick a `needs attention` scan id.
2. Open `images/<id>.query.jpg` (what the model scored) and `images/<id>.input.jpg` (what was uploaded).
3. Read `cases/<id>.json` for OCR hits, collector conflict, visual top-20, and whether the user confirmed, corrected, or rejected.

Confirmed rows become eval labels:

```bash
PYTHONPATH=api .venv/bin/python -m eval.harness --dataset datasets/review --out eval-report.json
```

`labels.jsonl` only includes scans with user feedback. Unconfirmed matches stay in `review.jsonl` as unverified.

## HTTP API

Set `REVIEW_TOKEN` (or use the helper credential), then:

```bash
curl -s -H "Authorization: Bearer $REVIEW_TOKEN" \
  "http://localhost:8000/api/v1/review?needs_attention=true"
curl -s -H "Authorization: Bearer $REVIEW_TOKEN" \
  "http://localhost:8000/api/v1/review/cases/<scan_id>"
curl -s -H "Authorization: Bearer $REVIEW_TOKEN" \
  -o query.jpg \
  "http://localhost:8000/api/v1/review/images/<scan_id>.query.jpg"
```

On staging the same paths are under `https://staging-scan.auctaro.com/api/v1/review`.

## Staging files

Dokploy stores captures on the data volume at `/data/review`. The review API reads that folder; you do not need to copy files down for inspection.
