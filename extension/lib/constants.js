export const PARSER_VERSION = "offers-v1";
export const IDLE_ALARM = "scanapp-cardmarket-idle";
export const WAIT_ALARM = "scanapp-cardmarket-wait";
export const RENEW_ALARM = "scanapp-cardmarket-renew";
export const IDLE_PERIOD_MINUTES = 0.5;
export const POLL_MS = 1_000;
export const NAV_SPACING_MS = 2_000;
export const PAGE_DEADLINE_MS = 60_000;
export const FETCH_TIMEOUT_MS = 8_000;
export const CLAIM_LIFETIME_MS = 180_000;
export const MAX_RECENT_FAILURES = 5;
export const MAX_EXPANSION_PAGES = 80;
export const MAX_EXPANSION_PRODUCTS = 5_000;
export const EXPANSION_PAGE_MS = 2_000;
export const SERVERS = {
  local: "http://127.0.0.1:8000",
  staging: "https://staging-scan.auctaro.com",
};
export const DEFAULT_API = SERVERS.local;
export const STORAGE_KEYS = [
  "apiBase",
  "helperToken",
  "paused",
  "currentJob",
  "pendingResult",
  "lastNavigationAt",
  "lastSuccessAt",
  "lastFailure",
  "recentFailures",
  "activity",
  "currentCard",
  "connection",
  "queued",
  "attention",
  "helperTabClosed",
];
