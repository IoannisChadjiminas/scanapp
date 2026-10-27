from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("/data")
    catalogue_backend: str = "sqlite"
    planetscale_database_url: SecretStr = SecretStr("")
    # Writable portfolio store: PlanetScale database pokesingle-product.
    # Empty keeps holdings in the local catalogue file for tests.
    portfolio_database_url: SecretStr = SecretStr("")
    # Server-to-server portfolio registration; never supplied to mobile clients.
    scanapp_service_token: SecretStr = SecretStr("")
    planetscale_schema: str = "pokesingle_import_20261001"
    planetscale_import_id: str = "PS-IMPORT-001-20261001"
    tmp_dir: Path = Path("/tmp/scanapp")
    preprocess_config: str = "pad"
    use_ocr: bool = True
    use_grading: bool = True
    # Opt-in: a separate OCR engine overlaps label work with card recognition.
    parallel_grading: bool = False
    # Return at card completion; unfinished/unidentified grading defaults Raw.
    grading_at_card_deadline: bool = False
    # Label OCR competes with card OCR for CPU. When on, skip uploads whose
    # client sent graded=false; graded=true or no hint are still graded. Off,
    # the hint is ignored and logged so a rollout can compare it with what
    # grading found.
    grading_requires_client_hint: bool = False
    # Retrieval windows may omit metadata. Try the supplied card-shaped frame
    # for OCR first, without changing the visual/artwork retrieval crop.
    ocr_complete_frame_first: bool = False
    # Keep initial OCR unchanged; omit optional footer retries only for a
    # strongly supported, reviewable identity. Never certify its printing.
    ocr_adaptive_footer: bool = False
    # Requires ocr_adaptive_footer. Read only the title strip when the visual
    # leader has exactly one same-art printing and both visual streams agree.
    # A policy change: replay the frozen panel before enabling it.
    ocr_title_only_single_printing: bool = False
    # Order an unproven printing group by a footer fraction read with look-alike
    # characters ("00z/03" for 007/034). Reorders only; never confirms a printing.
    ocr_damaged_footer_order: bool = False
    # Order an unproven printing group by the printing the phone's own name and number name (set totals
    # applied), when that card is among the candidates. Reorders only; the status stays printing_ambiguous.
    ocr_printing_from_text: bool = False
    # One isolated footer reader overlaps initial title/footer inference.
    # Its auxiliary CPU lane is shared with optional grading, not added to it.
    ocr_parallel_regions: bool = False
    # Opt-in recovery for readable full cards whose holo artwork scores poorly.
    # Exact printed identity plus distributed reference-layout geometry permits
    # review only; automatic match thresholds and artwork proof stay unchanged.
    structured_layout_recovery: bool = False
    # One focused title read for unresolved, unrelated candidate lists.
    # A changed result requires independent local artwork verification.
    ocr_conflict_title_retry: bool = False
    # Text-detector short-side target in pixels (RapidOCR Det.limit_side_len, limit_type min).
    # 0 keeps the library default (736). Smaller is cheaper but can change OCR text; a policy
    # change: replay the frozen panel before enabling it.
    ocr_det_limit_side_len: int = 0
    # Skip every optional OCR retry pass (weak header, small footer, footer halves); only the
    # title and footer reads run. Cheaper, but a retry can recover a number the first read missed.
    # A policy change: replay the frozen panel on the full catalogue before enabling it.
    ocr_skip_retry_passes: bool = False
    # Never take a grading-label word (PRISTINE, GEM MINT, PSA, a cert number...) as the card
    # name; with a label in the title strip, prefer a title read after it. A policy change:
    # replay the frozen panel before enabling it.
    ocr_label_name_filter: bool = False
    # Read a set code glued to the front of a fraction (30C077/128, SV077/198) as the set
    # code, not as part of the number, and accept a promo set's own prefix (MEP078 for
    # catalogue 078). Only removes false conflicts; names and totals still apply. A policy
    # change: replay the frozen panel before enabling it.
    ocr_set_code_prefix: bool = False
    # A promo prefix one letter off its set id (MP078, ME078 for MEP078) agrees with that promo
    # card when the number is the same 3 digits, and a bare 078 agrees only when the name and
    # number name exactly one promo card. Restricted to the promo set table; never a
    # different number, a two-letter error or an unrelated set. A policy change: replay first.
    ocr_promo_prefix_near: bool = False
    # When an abstaining scan has a confident printed fraction plus a name read anywhere in
    # its OCR lines that together narrow the catalogue to 1-3 cards, add those cards as
    # candidates for local artwork verification and, if unverified, return them as
    # suggestions needing confirmation instead of an empty retake. A verified single
    # candidate also skips the boundary retry. Never overrides a confident visual answer.
    text_identity_candidates: bool = False
    # Requires text_identity_candidates. Parse a slab label's set line and number ("Burning
    # Shadows - 18a/147", PSA "#18A") into catalogue candidates, and also try them when a
    # near-threshold visual leader agrees with neither the label nor the card's printed name.
    slab_label_identity: bool = False
    # Requires text_identity_candidates. When no card frame was found and the title/footer
    # strips read no printed number (a screenshot's status and browser bars), read the whole
    # upload once (~1,400 px) and feed its lines to the number+name and label paths.
    full_image_text_fallback: bool = False
    # Slab text repairs: PSA labels whose set name is not the catalogue's (label name +
    # number + language, "#17HOLO", "JP", set aliases), the set line under a dated label
    # header is never the name, a footer fraction with an unknown denominator (017/012)
    # falls back to its numerator + name, and an artwork-verified label card is not vetoed
    # by a footer number that contradicts the label.
    slab_text_recovery: bool = False
    # Read the phone's own OCR of the card (client_text on POST /scans) and log how it
    # agrees with the server. Off: the field is ignored. It never chooses a card.
    client_text_hints: bool = False
    # When the phone's name and collector number confirm a clear visual/artwork leader
    # with a single printing for that number, skip the optional OCR re-reads (weak
    # header, footer halves, original-upload re-read). Any disagreement keeps the full
    # path. A policy change: replay the frozen panel before enabling it.
    client_text_fast_path: bool = False
    # Both phone fields must be at least this confident for the fast path.
    client_text_min_confidence: float = 0.9
    # Let the phone's read stand in for server OCR when it confirms the visual leader with
    # one printing for that number. 'footer': the server reads only the title and takes the
    # number from the phone; 'all': the server reads no card text. 'off' (default): never.
    # The phone's text then becomes evidence: replay the frozen panel before enabling it.
    client_text_ocr: str = 'off'
    # Optional NDJSON progress stream; legacy scans remain a single JSON response.
    scan_stream_results: bool = True
    enable_matched: bool = True
    # Near-tied preview printings show the requested or phone language first. Order only.
    preview_language_order: bool = True
    ort_intra_threads: int = 1
    # The image model runs alone on the critical path to the preview; OCR keeps ort_intra_threads.
    dino_intra_threads: int = 0
    ort_inter_threads: int = 1
    max_image_pixels: int = 12_000_000
    max_upload_bytes: int = 12_582_912
    scan_wait_limit: int = 2
    # Scans recognized at once in this process. Each lane adds its own OCR readers and
    # label/region workers but shares the loaded models and indexes; 1 keeps one scan at a time.
    scan_lanes: int = Field(default=1, ge=1, le=8)
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    session_cookie: str = "scanapp_session"
    session_ttl_days: int = 30
    store_captures: bool = True
    # Only with STORE_CAPTURES on: also keep the exact upload bytes beside the review copies.
    store_original_uploads: bool = False
    review_token: str = ""
    session_create_hourly: int = 30
    cardmarket_helper_enabled: bool = False
    cardmarket_webview_enabled: bool = True
    cardmarket_challenge_fallback_minutes: int = 10
    # How long the card page trusts a stored read before the phone reads again.
    cardmarket_price_fresh_minutes: int = 360
    # A listing read is the card's value this long. After that the daily price
    # file's trend is shown instead.
    cardmarket_listing_max_age_days: int = 7
    # A listing sample stays fresh longer for cheap cards. Pairs of
    # "trend in EUR up to : seconds fresh"; "*" closes the list. A card with no
    # known trend keeps the plain window above. CARDMARKET_FRESH_BY_VALUE=false
    # turns this off.
    cardmarket_fresh_by_value: bool = True
    cardmarket_fresh_tiers: str = "2:518400,20:172800,*:86400"
    scraper_enabled: bool = False
    scraper_url: str = ""
    scraper_api_key: str = ""
    scraper_session_hourly: int = 10
    scraper_ip_hourly: int = 20
    scraper_daily_pages: int = 50
    scraper_daily_mb: int = 50
    scraper_reserve_kb: int = 500
    scraper_url_cooldown_s: int = 1800
    scraper_attempt_seconds: int = 70
    scraper_page_gap_s: float = 0
    scraper_browser_lifetime_s: float = 1800
    scraper_urls: str = ""
    cardmarket_interactive_start_s: int = 30
    scraper_interactive_reserve_pages: int = 0
    scraper_breaker_failures: int = 3
    scraper_breaker_base_s: float = 30
    scraper_breaker_max_s: float = 300
    daily_prices_enabled: bool = False
    # Cardmarket's public nightly price file and TCGdex prices. Neither needs
    # a browser, a proxy or a login.
    price_guide_enabled: bool = True
    price_guide_url: str = (
        "https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json"
    )
    tcgdex_prices_enabled: bool = True
    tcgdex_base_url: str = "https://api.tcgdex.net/v2"
    # Cards refreshed per night, and the pause between requests.
    tcgdex_prices_batch: int = 300
    tcgdex_prices_gap_s: float = 0.25
    daily_gap_min_s: float = 5
    # Each gap is stretched or shortened by up to this fraction at random.
    daily_gap_jitter: float = 0.3
    # Trend up to EUR : days between nightly reads. "*" closes the list. A card
    # with no known trend is read every night.
    daily_tiers: str = "2:6,20:2,*:1"
    # A card is read tonight whatever its tier when the price file's trend has
    # moved this many percent from the trend on its last listing read.
    daily_move_pct: float = 10.0
    # The night's reads should be finished by this UTC time (HH:MM).
    daily_deadline_utc: str = "08:00"
    daily_gap_max_s: float = 60
    daily_gap_step_s: float = 5
    daily_session_pages: int = 30
    daily_session_rotate_before_s: float = 120
    daily_browsers: int = 1
    # Holdings of an install that has not synced in this many days are not
    # read overnight. 0 keeps every holding. Needs the synced_at column.
    daily_install_max_age_days: int = 30
    photo_scrape_active: bool = False
    config_ttl_s: int = 600
    # Tell the phone (GET /config) to look for a graded slab on each photo and
    # send graded=true/false. Off until switched on here, no app rebuild.
    app_slab_detection: bool = False
    # Tell the phone (GET /config) to read the card's name and collector number on
    # the device and send them as client_text. Off until switched on here.
    app_client_text: bool = False
    # Slab label fields, a phone embedding, and photo quality. The phone sends
    # them only when asked. Logged only; none of them changes a scan's answer.
    app_client_label: bool = False
    app_client_embedding: bool = False
    app_client_quality: bool = False
    # Raw collector-number reads the phone could not validate (PokeSingle #161). The server
    # repairs them against the catalogue (stage1_number_repair). On by default (owner's call);
    # it only matters where stage 1 itself is on.
    app_client_number_candidates: bool = True
    # Stage 1 answers from the phone's vector and text. Off until staging turns it on.
    # Production stays off until the background check has stayed clean.
    stage1_early_exit: bool = False
    stage1_background_check: bool = False
    stage1_sample_rate: float = 1.0
    stage1_require_confirmation: bool = True
    stage1b_text_verify: bool = False
    # Real-scan fixes: independently opt in on staging, never by code default.
    stage1_set_totals: bool = False
    stage1_normalize_duplicates: bool = False
    stage1_printing_groups: bool = False
    stage1_promo_numbers: bool = False
    stage1_diagnostics: bool = False
    # Android fast-path fixes: each opts in on staging only, never by code default.
    stage1_number_repair: bool = True
    stage1_fuzzy_name: bool = False
    stage1b_server_frame: bool = False
    # Stage 1b abstains when the text names printing twins (same name and number, other printing)
    # and only the artwork would pick one. The full pipeline answers those instead. Off in code.
    stage1_twin_guard: bool = False
    # A vector whose leader is another printing of the text's own card (same name, other set or
    # language) is not a contradiction; the text's number and set total still pick the printing.
    # Footer-excluded printings: a same-name row whose known set total differs from the footer's total
    # (`9/108`) is not a candidate for the leader. The text card's own total must agree. Off until the
    # benchmark (api/scripts/stage1_bench) passes; see docs/family-rule-narrow-plan-20261026.md.
    stage1_family_vector: bool = False
    # Stage 1b with no server frame: frame the artwork check on the phone's corners (when card-shaped)
    # or on the whole upload. The artwork check still runs. Off until measured.
    stage1b_frame_fallback: bool = False
    # Phone photo prep, sent through GET /config. Defaults match the app today.
    app_capture_preset: str = 'max'
    app_jpeg_quality: int = 95
    # Longest side of the photo the app uploads, in pixels.
    app_max_edge: int = 2000
    app_native_codec: bool = False
    # Outline the card live in the camera view (iPhone; others keep the guide).
    app_live_outline: bool = True
    # Take the photo by itself once the live outline locks on (needs app_live_outline).
    app_auto_capture: bool = True
    # Use the app's own iPhone camera (card found on every frame) instead of the
    # camera plugin. Off until the native camera has been checked on a phone.
    app_native_camera: bool = False
    # The same for Android's own camera. Separate so Android can be switched on
    # and off without touching iPhone. Off until checked on an Android phone.
    app_native_camera_android: bool = False
    # Let a card count anywhere in the camera view, not only inside the middle box.
    app_card_anywhere: bool = True
    # Measure each photo on the phone as it is taken, against threshold_blur at
    # threshold_blur_edge, and take an automatic photo again when it is blurry.
    app_photo_check: bool = True
    # Largest share of the card's middle the phone lets be blown out to white
    # before it takes the photo again (0 = glare is not checked).
    app_max_glare: float = 0.08
    # How many times the phone takes an automatic photo again before sending
    # its best try anyway, for the server to judge.
    app_auto_retakes: int = 2
    # Tell the phone to find and flatten the card before upload.
    app_card_warp: bool = False
    # Honour skip_detect from the phone. Off: the server still runs its own
    # detection on a phone-flattened photo, so both can be compared first.
    trust_client_warp: bool = False
    # The phone's card corners as a first frame hypothesis. The server's own detection still runs and wins on disagreement.
    use_client_quad: bool = False
    scan_price_start_on_provisional: bool = True
    scan_price_candidate_reads: int = 2
    scan_price_warm_reader: bool = True
    scan_price_show_stale: bool = True
    scan_price_stale_max_days: int = 30
    # off: never. fallback: the phone asks after its own read fails.
    # parallel: the server queues a paid read when a confident scan has no fresh price.
    scan_price_server_read: str = "fallback"
    scan_price_server_read_statuses: str = "matched"
    scan_price_server_read_delay_ms: int = 3000
    scan_price_server_read_daily_pages: int = 0
    # No paid read for a card whose Cardmarket trend is below this (EUR). A card
    # with no known trend is still read. 0 reads every card.
    # 0 = no flat floor: the value tiers in CARDMARKET_FRESH_TIERS decide.
    scan_price_server_read_min_trend: float = 0.0

    ranking_version: str = "rank-v15-holder-printing-review"
    # Opt-in only; an invalid explicitly configured bundle fails validation.
    artwork_bundle_dir: Path | None = None
    # Immutable, catalogue-bound local geometry/printing probes. Opt-in only.
    reference_features_dir: Path | None = None
    ocr_version: str = "rapidocr-ppocrv6-small-regions-v7-layout-orientation"
    model_name: str = "dinov2-small"

    @property
    def catalog_sqlite(self) -> Path:
        return self.data_dir / "catalog.sqlite"

    @property
    def results_sqlite(self) -> Path:
        return self.data_dir / "results.sqlite"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def vectors_dir(self) -> Path:
        return self.data_dir / "vectors" / self.snapshot_name

    @property
    def snapshot_name(self) -> str:
        return self.preprocess_config

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "reference-images"

    @property
    def review_dir(self) -> Path:
        return self.data_dir / "review"

    @property
    def dinov2_path(self) -> Path:
        return self.models_dir / "dinov2_small.onnx"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def lane_urls(self) -> list[str]:
        raw = [item.strip() for item in self.scraper_urls.split(",") if item.strip()]
        if raw:
            return raw
        return [self.scraper_url] if self.scraper_url else []

    def scan_candidate_reads(self) -> int:
        return max(0, min(int(self.scan_price_candidate_reads), 3))

    def scan_server_read_mode(self) -> str:
        mode = (self.scan_price_server_read or "").strip().lower()
        if mode in {"off", "fallback", "parallel"}:
            return mode
        return "fallback"

    def scan_server_read_statuses(self) -> set[str]:
        return {
            item.strip()
            for item in self.scan_price_server_read_statuses.split(",")
            if item.strip()
        }

    def interactive_reserve_pages(self) -> int:
        if self.scraper_interactive_reserve_pages > 0:
            return self.scraper_interactive_reserve_pages
        return max(1, int(self.scraper_daily_pages * 0.2)) if self.scraper_daily_pages else 0

    threshold_min_visual: float = Field(default=0.78)
    threshold_min_visual_ocr: float = Field(default=0.70)
    threshold_min_gap: float = Field(default=0.04)
    threshold_blur: float = Field(default=40.0)
    # Sharpness is measured on a copy shrunk to this long edge (0 = as supplied) so it
    # does not depend on how large the phone's upload was; the limit is for that size.
    threshold_blur_edge: int = Field(default=1000)
    threshold_min_side: int = Field(default=180)


@lru_cache
def get_settings() -> Settings:
    return Settings()
