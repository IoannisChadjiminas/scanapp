from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ScanStatus(str, Enum):
    matched = "matched"
    no_match = "no_match"
    uncertain = "uncertain"
    printing_ambiguous = "printing_ambiguous"
    retake = "retake"
    failed = "failed"


class FeedbackAction(str, Enum):
    confirm = "confirm"
    correct = "correct"
    reject = "reject"


class CardmarketPrice(BaseModel):
    label: str
    amount: float
    currency: str = "EUR"


class CardmarketVariant(BaseModel):
    url: str
    slug: str = ""
    label: str = ""
    card_id: str | None = None
    expansion: str = ""
    code: str = ""
    number: str = ""
    price_text: str = ""
    image: str = ""


class Candidate(BaseModel):
    card_id: str
    name: str
    set_name: str
    collector_number: str
    image_url: str
    visual_score: float
    combined_score: float
    ocr_consistent: bool | None = None
    language: str = ""
    rarity: str = ""
    cardmarket_url: str | None = None
    cardmarket_prices: list[CardmarketPrice] = Field(default_factory=list)
    cardmarket_variants: list[CardmarketVariant] = Field(default_factory=list)
    retrieved_via: list[str] = Field(default_factory=list)
    artwork_score: float | None = None
    artwork_profile: str | None = None


class OcrEvidence(BaseModel):
    name_text: str | None = None
    collector_text: str | None = None
    lines: list[str] = Field(default_factory=list)
    failed: bool = False
    collector_retry_used: bool = False
    collector_retry_contributed: bool = False
    collector_retry_skipped: bool = False


class GradingEvidence(BaseModel):
    """Observed label text, not authentication or a photographic condition grade."""

    slab_detected: bool | None = None
    is_graded: bool | None = None
    grading_status: Literal["unknown", "graded", "authenticated_only", "ungraded"] = "unknown"
    company: Literal["psa", "beckett", "cgc", "tag", "ace", "ags"] | None = None
    company_source: Literal["label_ocr", "label_ocr_fuzzy", "verified_logo", "none"] = "none"
    grade: float | None = Field(default=None, ge=1, le=10)
    condition_label: str | None = None
    subgrades: dict[str, float] = Field(default_factory=dict)
    tag_score: int | None = Field(default=None, ge=1, le=1000)
    certification_number: str | None = None
    qualifiers: list[str] = Field(default_factory=list)
    raw_condition: Literal["not_assessed"] = "not_assessed"
    authenticity_verified: Literal[False] = False
    source: Literal["visible_label_ocr", "none"] = "none"
    requires_confirmation: bool = True
    label_text: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RecognitionConfidence(BaseModel):
    """Raw evidence, not a calibrated percentage of successful recognition."""

    probability: float | None = Field(default=None, ge=0, le=1)
    calibration_status: str = "uncalibrated"
    candidate_card_id: str | None = None
    visual_similarity: float | None = None
    artwork_similarity: float | None = None
    visual_margin: float | None = None
    name_ocr_confidence: float | None = None
    collector_ocr_confidence: float | None = None
    identity: str = "unknown"
    printing: str = "unconfirmed"
    finish: str = "unconfirmed"
    requires_confirmation: bool = True
    retake_recommended: bool = False
    reasons: list[str] = Field(default_factory=list)


class PlausiblePrinting(BaseModel):
    card_id: str
    name: str
    set_name: str
    collector_number: str
    language: str
    image_url: str
    cardmarket_url: str | None = None


class PrintingReview(BaseModel):
    reason: str
    candidate_group_id: str
    grouping_basis: str = "reference_similarity_or_near_tied_retrieval"
    reference_coverage_complete: bool = False
    collector_evidence: list[str] = Field(default_factory=list)
    plausible_printings: list[PlausiblePrinting]
    guidance: str


class MatchOption(PlausiblePrinting):
    """A display choice; absent retrieval scores stay unknown, not fabricated."""

    language: str = ""
    visual_score: float | None = None
    combined_score: float | None = None
    artwork_score: float | None = None
    ocr_consistent: bool | None = None
    rarity: str = ""
    retrieved_via: list[str] = Field(default_factory=list)
    cardmarket_prices: list[CardmarketPrice] = Field(default_factory=list)
    cardmarket_variants: list[CardmarketVariant] = Field(default_factory=list)
    source: Literal["retrieval", "printing_review"] = "retrieval"
    selection_action: Literal["confirm", "correct"] = "confirm"


class MatchPresentation(BaseModel):
    best_match: MatchOption | None = None
    alternatives: list[MatchOption] = Field(default_factory=list)
    match_state: Literal["matched", "likely", "tentative", "unavailable"] = "unavailable"


class LanguageCoverage(BaseModel):
    language: str
    cards: int
    indexed: int


class Coverage(BaseModel):
    cards: int
    indexed: int
    missing_images: int
    languages: list[LanguageCoverage] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    ready: bool
    catalogue_version: str | None = None
    model_revision: str | None = None
    preprocess_config: str
    use_ocr: bool
    snapshot: str
    coverage: Coverage | None = None
    detail: str | None = None
    catalogue_backend: str = "sqlite"
    catalogue_import_id: str | None = None


class PrepareResponse(BaseModel):
    mime_type: str = "image/jpeg"
    width: int
    height: int
    image_base64: str
    converted: bool


class ScanResponse(MatchPresentation):
    id: str
    status: ScanStatus
    suggestions: list[Candidate]
    ocr: OcrEvidence
    coverage: Coverage
    timings_ms: dict[str, float]
    versions: dict[str, str]
    message: str | None = None
    detected_language: str | None = None
    search_languages: list[str] = Field(default_factory=list)
    printing_review: PrintingReview | None = None
    confidence: RecognitionConfidence | None = None
    grading: GradingEvidence = Field(default_factory=GradingEvidence)


class FeedbackRequest(BaseModel):
    action: FeedbackAction
    card_id: str | None = None
    cardmarket_url: str | None = None
    printing_selected: bool = False


class FeedbackResponse(BaseModel):
    id: str
    action: FeedbackAction
    confirmed_card_id: str | None = None


class CardSummary(BaseModel):
    id: str
    name: str
    set_id: str
    set_name: str
    collector_number: str
    language: str
    rarity: str = ""
    has_image: bool
    image_url: str | None = None
    variants: dict[str, Any] = Field(default_factory=dict)
    cardmarket_url: str | None = None
    cardmarket_variants: list[CardmarketVariant] = Field(default_factory=list)


class CardSearchResponse(BaseModel):
    items: list[CardSummary]
    total: int


class SessionResult(MatchPresentation):
    scan_id: str
    created_at: datetime
    status: ScanStatus
    suggestions: list[Candidate]
    confirmed_card_id: str | None = None
    chosen_cardmarket_url: str | None = None
    rejected: bool
    timings_ms: dict[str, float] = Field(default_factory=dict)
    printing_review: PrintingReview | None = None
    confidence: RecognitionConfidence | None = None
    grading: GradingEvidence = Field(default_factory=GradingEvidence)


class SessionResultsResponse(BaseModel):
    session_id: str
    results: list[SessionResult]
    coverage: Coverage | None = None
