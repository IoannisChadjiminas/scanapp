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
export const MAX_EXPANSIONS = 2_000;
export const DEFAULT_PACE = "fast";
export const PACE_PROFILES = {
  fast: {
    readMin: 0,
    readMax: 0,
    pageMin: 0,
    pageMax: 0,
    setMin: 0,
    setMax: 0,
    thinkMin: 0,
    thinkMax: 0,
    settleMin: 0,
    settleMax: 0,
    breakEveryMin: 4,
    breakEveryMax: 11,
    breakMin: 0,
    breakMax: 0,
    hesitateChance: 0,
    hesitateMin: 0,
    hesitateMax: 0,
  },
  medium: {
    readMin: 1_200,
    readMax: 4_000,
    pageMin: 3_000,
    pageMax: 8_000,
    setMin: 6_000,
    setMax: 14_000,
    thinkMin: 600,
    thinkMax: 2_200,
    settleMin: 1_500,
    settleMax: 4_500,
    breakEveryMin: 5,
    breakEveryMax: 10,
    breakMin: 15_000,
    breakMax: 45_000,
    hesitateChance: 0.08,
    hesitateMin: 3_000,
    hesitateMax: 12_000,
  },
  slow: {
    readMin: 2_500,
    readMax: 8_000,
    pageMin: 6_000,
    pageMax: 16_000,
    setMin: 12_000,
    setMax: 28_000,
    thinkMin: 1_200,
    thinkMax: 4_500,
    settleMin: 3_000,
    settleMax: 9_000,
    breakEveryMin: 4,
    breakEveryMax: 11,
    breakMin: 35_000,
    breakMax: 90_000,
    hesitateChance: 0.16,
    hesitateMin: 6_000,
    hesitateMax: 24_000,
  },
};
export const SERVERS = {
  local: "http://127.0.0.1:8000",
  staging: "https://staging-scan.auctaro.com",
};
export const DEFAULT_API = SERVERS.local;
export const STORAGE_KEYS = [
  "apiBase",
  "helperToken",
  "helperTokens",
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
  "expansionResume",
  "ntfyTopic",
  "expansionPace",
];
