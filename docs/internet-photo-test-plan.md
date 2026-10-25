# Plan: test stage 1 at volume with real-world card photos from the internet

**Goal:** collect **300–500 real-world photos** of Pokémon cards from public listing pages, label them, run each one through **the phone's own pipeline on a real iPhone**, and send it to **staging** exactly like an app scan. Then measure stage 1 / 1b, wrong answers and background-check disagreements at volume.

**Repos:**
- **ScanApp** (`~/WebstormProjects/scanapp`): the collection and labeling scripts in `api/scripts/photo_corpus/`, and the report.
- **PokeSingle** (`~/StudioProjects/PokeSingle`): the diagnostic harness gets a "send to staging" mode. It builds on draft PR #157 (`f8bd7f8`).

**This is internal testing only.** Open PRs and don't merge them; nothing is published.

## Collection rules (must follow)

The owner confirmed permission for eBay photos to be used in this internal evaluation corpus and chose the official Browse API after creating an eBay developer account. Use the API instead of scraping listing pages:
- Use production Browse API search and the listing's primary image only. Credentials stay outside the repository in `~/.config/scanapp-photo-corpus/ebay.env` (mode 600); never print or commit them. Request only the client-credentials OAuth scope needed for Browse.
- **Slow and identifiable:** at most **1 request every 3–5 seconds per host**, a descriptive User-Agent with a contact address, and a daily cap (e.g. 500 search pages). Cache search responses after stripping all seller and unneeded fields; never refetch cached pages or already-collected item IDs.
- **Photos stay private:** store them under `data/photo-corpus/` (gitignored) or a private bucket. **Never commit photos to git**, publish or redistribute them, and delete them when the experiment ends unless the owner decides otherwise.
- **No personal data:** skip or blur photos with faces, names, addresses or handwriting beyond the card. Do not retain seller names or usernames.
- If API access is denied or an endpoint blocks requests, stop collection and report the status; do not use scraping, proxying, or challenge bypasses as a fallback.

## 1. Collect (ScanApp, `api/scripts/photo_corpus/collect.py`)

**Sources**, in order:
1. **eBay Browse API:** primary listing photos plus listing titles. Searches like `pokemon card <set name>`, `psa 10 pokemon <set>`, `cgc pokemon`, `pokemon base set charizard 4/102`. Use `api/scripts/photo_corpus/collect.py`.
2. **Reddit public posts** (e.g. r/PokemonTCG, r/pkmntcg trade threads) via the public `.json` endpoints: the post images plus the title.
3. **Cardmarket** (often behind Cloudflare): only with the owner solving any challenge by hand, as above. Skip sites that only have **stock scans** (TCGplayer product images), because those aren't real photos.

**Target mix** (about 400 photos):

| Bucket | Photos |
|---|---|
| Modern raw (SV, SWSH, SM) | 100 |
| Vintage WOTC raw (Base, Jungle, Fossil, Base Set 2, Rocket, Gym, Neo, e-Card) | 80 |
| Same-artwork reprints (Base Set vs Celebrations Classic Collection vs Evolutions vs 30th Celebration vs Base Set 2, Legendary Collection) | 40 |
| Japanese raw | 50 |
| Slabs (PSA, CGC, BGS, ACE…) | 80 |
| Hard cases (sleeves, toploaders, glare, angled, binder pages) | 50 |

**Save per photo:** the image (original bytes), source site, the page URL (kept privately for re-checks), the listing title, and the photo index within the listing. **Use only the main photo** of each listing (the front of the card), and skip back-of-card photos when the title or detection shows them.

## 2. Label (ScanApp, `api/scripts/photo_corpus/label.py`)

1. **A first guess from the title:** parse the set name, card name and number from the title (e.g. `Charizard 4/102 Base Set Holo PSA 9`). Match it against the catalogue with the same rules as the server (set totals, duplicate IDs, the reprint groups from PR #67).
2. **Run the full server pipeline** (local, read-only catalogue, no phone hints) on each photo. That gives a second opinion.
3. **Agreement** between the title guess and the server's top card means `auto-labeled`. **Disagreement or no guess** means `needs review`.
4. **A review sheet** (a CSV, or a small local HTML page) for the owner: the photo, title, title guess and server top 3, with one click to pick the right card or "skip". Only `auto-labeled` plus `reviewed` photos count as ground truth.

**Deliverable:** `data/photo-corpus/labels.csv` with photo, bucket, card ID and label source.

## 3. Run through the phone (PokeSingle harness, a "send to staging" mode)

Extend the diagnostic harness from PR #157:
- **Load photos** from a folder copied into the app's private diagnostic folder (as the vintage test did).
- **For each photo, run the app's own production code path** for a **gallery import**: still-photo card detection (corners), the shared text pass (name, number, slab label fields), the quality check and the Core ML embedding. **Use the same deadlines as real scans.**
- **POST to the staging scanner** exactly like the app: the same multipart fields (`image`, `card_quad`, `quad_source`, `client_text`, `client_embedding`, `client_quality`, `graded`, `stream_results`) and the same `platform`, `capture=gallery` and `build`. Add a field or header like `diagnostic_run=<run_id>`, so these scans can be filtered in the logs and excluded from user analytics.
- **Save per photo:** the phone timings, the fields sent, and the server's response (status, card, stage).
- **Run in batches of about 50,** with pauses, so the staging queue stays healthy (`SCAN_WAIT_LIMIT=2`). Don't run while real testers are scanning.
- **Android:** if a device is connected, run the same mode there too (no embedding unless B2 is approved).

## 4. Report (ScanApp, `docs/experiments/internet-photo-test-<date>.md`)

Join the harness results with the labels and the staging logs (`stage0`, `stage1_check`, `scan_summary` lines for that `diagnostic_run`).

**Per bucket:**
- **Stage 1 / stage 1b / full pipeline:** answer counts and the share of each
- **Correct and wrong:** for stage 1 / 1b answers **(must be 0 wrong)** and for the full pipeline top card
- **Background-check disagreements**
- **Phone time** (median and p90) and **server time** per path
- **Phone read rates:** corners, name, number, label

**Lists:**
- **every wrong answer and every disagreement:** photo, expected card, the answer, and why
- **the top miss reasons** (no corners, no number, ambiguous text, visual contradiction, missing reference image…)
- **look-alike reprint results** (the Charizard 4/102 vs Celebrations case)

**Recommendations:**
- **turning stage 1 on in production:** yes or no, and at what sample rate for the background check
- **the next fixes,** ranked by how many photos they'd unlock

## Done when

- **Photos:** 300–500 collected under the rules above, with sources and any challenge pauses recorded.
- **Labels:** at least 90% labeled (auto or reviewed).
- **Phone harness:** the "send to staging" mode is in a PokeSingle PR, not merged.
- **ScanApp:** the scripts and the report are in a PR, not merged, with **no photos in git**.
- **Cleanup:** staging is restored to normal afterwards, with no config changes left behind.
