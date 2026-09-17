export type ScanStatus = "matched" | "no_match" | "uncertain" | "retake" | "failed";

export type CardmarketPrice = {
  label: string;
  amount: number;
  currency: string;
};

export type CardmarketPriceResponse = {
  url: string | null;
  prices: CardmarketPrice[];
  status?: string | null;
  helper_online?: boolean;
  helper_ready?: boolean;
  helper_paused?: boolean;
  helper_attention?: string | null;
  observed_at?: string | null;
  sampled_offer_count?: number | null;
  freshness?: string | null;
  queued?: number | null;
};

export type Candidate = {
  card_id: string;
  name: string;
  set_name: string;
  collector_number: string;
  image_url: string;
  visual_score: number;
  combined_score: number;
  ocr_consistent: boolean | null;
  language?: string;
  cardmarket_url?: string | null;
  cardmarket_prices?: CardmarketPrice[];
};

export type Coverage = {
  cards: number;
  indexed: number;
  missing_images: number;
  languages?: { language: string; cards: number; indexed: number }[];
};

export type HealthResponse = {
  status: string;
  ready: boolean;
  catalogue_version: string | null;
  model_revision: string | null;
  preprocess_config: string;
  use_ocr: boolean;
  snapshot: string;
  coverage: Coverage | null;
  detail: string | null;
};

export type PrepareResponse = {
  mime_type: string;
  width: number;
  height: number;
  image_base64: string;
  converted: boolean;
};

export type ScanResponse = {
  id: string;
  status: ScanStatus;
  suggestions: Candidate[];
  ocr: {
    name_text: string | null;
    collector_text: string | null;
    lines: string[];
    failed: boolean;
  };
  coverage: Coverage;
  timings_ms: Record<string, number>;
  versions: Record<string, string>;
  message: string | null;
  detected_language?: string | null;
  search_languages?: string[];
};

export type CardSummary = {
  id: string;
  name: string;
  set_id: string;
  set_name: string;
  collector_number: string;
  language: string;
  has_image: boolean;
  image_url: string | null;
  variants: Record<string, unknown>;
  cardmarket_url?: string | null;
};

export type SessionResult = {
  scan_id: string;
  created_at: string;
  status: ScanStatus;
  suggestions: Candidate[];
  confirmed_card_id: string | null;
  rejected: boolean;
  timings_ms: Record<string, number>;
};

export type SessionResultsResponse = {
  session_id: string;
  results: SessionResult[];
  coverage: Coverage | null;
};
