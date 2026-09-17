from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ScanStatus(str, Enum):
    matched = "matched"
    no_match = "no_match"
    uncertain = "uncertain"
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
    cardmarket_url: str | None = None
    cardmarket_prices: list[CardmarketPrice] = Field(default_factory=list)


class OcrEvidence(BaseModel):
    name_text: str | None = None
    collector_text: str | None = None
    lines: list[str] = Field(default_factory=list)
    failed: bool = False


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


class PrepareResponse(BaseModel):
    mime_type: str = "image/jpeg"
    width: int
    height: int
    image_base64: str
    converted: bool


class ScanResponse(BaseModel):
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


class FeedbackRequest(BaseModel):
    action: FeedbackAction
    card_id: str | None = None


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
    has_image: bool
    image_url: str | None = None
    variants: dict[str, Any] = Field(default_factory=dict)
    cardmarket_url: str | None = None


class CardSearchResponse(BaseModel):
    items: list[CardSummary]
    total: int


class SessionResult(BaseModel):
    scan_id: str
    created_at: datetime
    status: ScanStatus
    suggestions: list[Candidate]
    confirmed_card_id: str | None = None
    rejected: bool
    timings_ms: dict[str, float] = Field(default_factory=dict)


class SessionResultsResponse(BaseModel):
    session_id: str
    results: list[SessionResult]
    coverage: Coverage | None = None
