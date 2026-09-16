# Scanapp: Next.js Visual Card Recognition Experiment

## 1. Objective and scope

Build in `/Users/ioannischadjiminas/WebstormProjects/scanapp`, following its `AGENTS.md` and bundled Next.js documentation.

**Hypothesis:** English Pokémon cards can be identified from real phone photos at useful accuracy and latency, including when the collector number is unreadable.

### First release

- Next.js browser interface with camera capture and photo upload.
- Visual identification with optional OCR evidence.
- Three suggestions, explicit uncertainty and user corrections.
- Anonymous session results and CSV export.
- Local Docker Compose operation and DigitalOcean deployment.

Use pretrained models with unchanged weights. No model training, accounts, collections, pricing, foil detection or Flutter development.

Uploaded photographs are deleted after processing. Benchmark photographs remain in a separate local dataset.

## 2. Architecture and recognition

### Stack

| Component | Choice |
|---|---|
| Frontend | Next.js App Router, React, TypeScript, Tailwind |
| UI components | shadcn/ui, added as needed and styled with shared Tailwind theme tokens |
| Frontend delivery | Static export served by Caddy |
| Backend | FastAPI and Pydantic |
| Image processing | OpenCV, Pillow and `pillow-heif` |
| Visual model | DINOv2 Small through ONNX Runtime |
| OCR | RapidOCR through ONNX Runtime |
| Metadata and results | SQLite |
| Vector retrieval | NumPy exact cosine similarity |
| Runtime | Docker Compose, CPU inference |

Use the maintained `rapidocr` package with explicitly configured ONNX Runtime CPU execution. Pin the package, small detection/recognition models and their checksums. The current RapidOCR documentation supports this setup. [RapidOCR installation](https://rapidai.github.io/RapidOCRDocs/main/en/install_usage/rapidocr/install/)

Keep Tesseract only in the development evaluation tooling for a comparison on 50 development photographs. Production runs RapidOCR alone.

### Catalogue and vectors

Import English Pokémon metadata and reference images from TCGdex. Preserve provider ID, name, set, collector number, language and variant metadata.

Keep separate artifacts:

```text
catalog.sqlite
embeddings.npy
embedding_card_ids.npy
manifest.json
```

Create a separate vector snapshot for each preprocessing configuration. The manifest records catalogue version, model revision, preprocessing configuration, dimensions and checksums.

Validate vector-to-card alignment at startup. Load or memory-map the selected snapshot once. Normal application startup must not download models or rebuild embeddings.

Display actual indexed catalogue coverage, including missing reference images.

### Image preparation experiment

Evaluate four configurations:

| Preparation | Matching |
|---|---|
| Full card, proportions preserved with padding | Visual only |
| Full card, proportions preserved with padding | Visual + RapidOCR |
| Full card resized to square | Visual only |
| Full card resized to square | Visual + RapidOCR |

Use identical model resolution and normalization across the comparison. Disable implicit center cropping.

**Reference images and query images must use the same preprocessing configuration.**

Select one configuration using development results, then deploy that configuration.

### Recognition flow

1. Decode JPEG, PNG, WebP or HEIC/HEIF.
2. Normalize orientation.
3. Detect the card boundary and rectify perspective when reliable.
4. Fall back to the user-adjusted crop when automatic detection is unreliable.
5. Prepare the full card for DINOv2 and calculate its normalized embedding.
6. Retrieve the closest 20 reference vectors.
7. Run RapidOCR on the name and collector-number regions, accommodating different card layouts.
8. Rerank using available text evidence.
9. Apply the uncertainty policy and return three suggestions.

OCR is secondary. Missing text must not block visual retrieval. Conflicting readable text can provide evidence against a candidate.

### Uncertainty

Return:

- `matched`: a candidate passes the validated selection rules.
- `uncertain`: evidence does not justify choosing one card.
- `retake`: the photograph is unsuitable for useful recognition.

Start with `uncertain` suggestions. Enable `matched` after selecting and freezing thresholds on development data.

Consider visual similarity, the gap between leading candidates and OCR consistency. Evaluate scans without readable numbers separately.

Never display similarity scores as probability percentages. Shared-artwork printings remain uncertain when their distinguishing details are absent.

## 3. Docker Compose: local and production

### Services

| Service | Responsibility |
|---|---|
| `web` | Caddy serves the exported Next.js app and proxies `/api/v1` to FastAPI |
| `api` | Recognition, catalogue search, session ownership and results |
| `bootstrap` | One-off model preparation, catalogue import and vector generation; enabled through a tools profile |

The two runtime containers require no Node.js, PyTorch or PaddlePaddle process. Build/export tooling may use additional dependencies outside the production runtime.

Use persistent Docker volumes for catalogue data, reference images, vectors and models. Keep temporary uploads separate and clean them on success and failure.

### Compose configuration

Provide:

- `compose.yaml`: shared service definitions.
- `compose.override.yaml`: automatically applied local settings.
- `compose.prod.yaml`: explicit DigitalOcean configuration.

Docker supports this base-plus-overrides approach. [Compose documentation](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/)

Support native Linux ARM64 for Apple Silicon Docker and Linux AMD64 for DigitalOcean. Verify model output consistency across both targets.

### Local startup

The intended first-run workflow, once implemented:

```bash
cd /Users/ioannischadjiminas/WebstormProjects/scanapp
cp .env.example .env
docker compose --profile tools run --build --rm bootstrap
docker compose up --build -d
```

Open:

```text
http://localhost:8080
```

Subsequent starts:

```bash
docker compose up -d
```

Stopping containers preserves the catalogue and indexes:

```bash
docker compose down
```

Bootstrap must be resumable and reuse completed downloads and artifacts. Its initial run requires internet access; recognition uses local assets afterward.

Model export, indexing and image builds may need more memory than the deployed application. The 2 GiB production target applies to steady-state runtime.

### Local phone testing

- Desktop browser camera testing works through `localhost`.
- Opening the computer’s plain HTTP LAN address from a phone does not satisfy browser camera requirements.
- Provide an optional local HTTPS configuration using Caddy’s internal certificate authority, with documented certificate installation and trust on the phone.
- Make LAN exposure an explicit local setting.
- Production uses a configured public hostname and automatically managed HTTPS.

[Browser camera requirements](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia), [Caddy HTTPS](https://caddyserver.com/docs/automatic-https)

### Production and resource limits

Benchmark DigitalOcean’s 2 vCPU / 2 GiB instance, then compare the cheaper 1 vCPU / 2 GiB instance. Deploy the cheaper configuration if it meets the same acceptance checks.

- Build images and prepare catalogue artifacts locally or in CI.
- Deploy ready-built images and the validated artifact snapshot.
- Run one FastAPI application worker.
- Load recognition models once.
- Permit one active scan initially, with bounded waiting.
- Limit inference-library threads and image dimensions.
- Measure total container and host memory.
- Return controlled busy responses when capacity is occupied.
- Expose only Caddy publicly.

Sharing ONNX Runtime does not eliminate the additional memory required by OCR models. The combined workload must demonstrate that it fits the target server.

## 4. Interface, APIs and records

### UI design with shadcn/ui

Use shadcn/ui as the default source for reusable interface components. Initialize it in the existing Next.js project during UI implementation, keeping the current TypeScript, Tailwind and import-alias setup. Add only components used by the app. [Next.js setup](https://ui.shadcn.com/docs/installation/next), [component catalogue](https://ui.shadcn.com/docs/components)

| UI need | Components |
|---|---|
| Capture, upload, confirm and retry actions | Button |
| Catalogue search and form fields | Input, Label |
| Match suggestions and recognition status | Card, Badge |
| Correction search and expanded card details | Dialog on desktop, Sheet on mobile |
| Scanner and session-results navigation | Tabs |
| Session measurements | Table with a mobile-friendly layout |
| Loading, empty and failure states | Skeleton, Empty, Alert |

- Use shared theme tokens for color, typography, spacing, borders and focus states.
- Design for phone screens first, with clear primary actions and touch targets of at least 44 by 44 CSS pixels.
- Keep the camera preview, card guide and crop interaction as purpose-built components, composed with shadcn/ui controls.
- Preserve keyboard navigation, visible focus, accessible names and dialog focus management; announce processing and result changes to assistive technology.
- Keep interactive components within the existing Client Component boundaries so static layout and content remain build-time rendered.

### Browser workflow

Provide:

1. Open camera or upload.
2. Card guide, manual capture, preview, rotation and crop.
3. Processing state.
4. Three suggestions with reference image, name, set and collector number.
5. Confirm, choose another, search catalogue, reject suggestions or scan again.
6. Session results and CSV export.

When the browser cannot preview an uploaded format, the backend returns a normalized JPEG for preview and cropping.

Handle camera permission denial, unsupported camera access, network errors, unreadable images and overload.

### Public API

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/images/prepare` | Produce a normalized preview for browser-incompatible uploads |
| `POST /api/v1/scans` | Recognize a card |
| `GET /api/v1/cards?q=...` | Search the catalogue |
| `POST /api/v1/scans/{id}/feedback` | Confirm, correct or reject suggestions |
| `GET /api/v1/session/results` | Retrieve the current anonymous session’s results |
| `GET /api/v1/health` | Report model and catalogue readiness |

Use anonymous session ownership to isolate results and feedback between testers. Generate frontend API types from FastAPI’s OpenAPI schema.

### Scan records

Record:

- Model, catalogue, preprocessing, OCR and ranking versions.
- Visual and combined candidate rankings.
- Targeted OCR output.
- Result status and threshold configuration.
- Confirmed card or rejection.
- Stage timings and processing failures.

Do not retain uploaded photos or their temporary derivatives.

### Framework practices

- Keep static layout and content as build-time Server Components.
- Use Client Components for camera controls and interactive data.
- Keep request-time backend behavior in FastAPI.
- Implement cancellation and explicit loading/error states.
- Release camera tracks and preview URLs.
- Keep CPU work outside the asynchronous request loop.
- Validate actual file contents, dimensions and upload size.
- Keep SQLite and internal artifacts outside the public web directory.

## 5. Evaluation and delivery

### Dataset

Use 300 development photographs and 300 holdout photographs, plus a separately reported unsupported-card set.

Split by card identity and capture session. Keep near-duplicate photographs together. Reference images for supported holdout cards remain in the search catalogue.

Include:

- Readable and obscured collector numbers.
- Similar reprints, promos and shared artwork.
- Sleeves, glare, blur and angles.
- Cropped edges, dark cards and busy backgrounds.
- iPhone and Android captures, including HEIC uploads.

Label photographs independently of predictions. Report representative everyday scans and difficult scans separately.

Freeze model artifacts, preprocessing, ranking and selection thresholds before holdout evaluation.

### Metrics and targets

Measure:

- Top-one and top-three accuracy.
- End-to-end success including failed scans.
- Accuracy with and without readable numbers.
- Confident-match errors divided by all confident matches.
- Coverage and abstention rate.
- Incorrect confident matches on unsupported cards.
- Median and 95th-percentile latency.
- Stage timings, peak memory and overload behavior.

Initial targets:

- At least 95% top-one and 98% top-three accuracy.
- Under five seconds at the 95th percentile with one active scan.
- At most 1% observed confident-match errors at at least 80% coverage.

Report sample counts and statistical uncertainty. These are experiment targets, not guarantees. If confident matching fails, retain uncertainty-first suggestions.

### Verification

- Playwright: scanner flow, corrections, session isolation, errors, keyboard navigation, dialog focus and mobile layouts.
- Python: preprocessing, vector mapping, OCR failure behavior and ranking.
- Integration: real inference, HEIC decoding, invalid uploads and cleanup.
- Docker: clean bootstrap, restart persistence, readiness and both CPU architectures.
- Devices: iPhone Safari and Android Chrome.
- Deployment: repeated scans and bounded overload on candidate Droplets.

### Delivery order

1. Add Compose services and reproducible bootstrap tooling.
2. Import the catalogue and create versioned model/index artifacts.
3. Implement recognition and the preprocessing/OCR evaluation harness.
4. Measure accuracy, latency and memory.
5. Initialize shadcn/ui and build the Next.js scanner, corrections and session results with the required components.
6. Freeze the selected development configuration.
7. Verify local Docker operation and phone HTTPS access.
8. Deploy to DigitalOcean and evaluate the holdout.

**Deliverable:** the same Next.js scanner runs locally through Docker Compose and on DigitalOcean, with measured recognition quality and no model training.
