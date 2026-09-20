export const PARSER_VERSION = "offers-v1";
export const IDLE_ALARM = "scanapp-cardmarket-idle";
export const WAIT_ALARM = "scanapp-cardmarket-wait";
export const RENEW_ALARM = "scanapp-cardmarket-renew";
export const IDLE_PERIOD_MINUTES = 0.5;
export const POLL_MS = 1_000;
export const NAV_SPACING_MS = 2_000;
export const PAGE_DEADLINE_MS = 60_000;
export const FETCH_TIMEOUT_MS = 8_000;
export const CHALLENGE_WATCH_MS = 750;
export const CHALLENGE_WATCH_TICKS = 240;
export const CLAIM_LIFETIME_MS = 180_000;
export const MAX_RECENT_FAILURES = 5;
export const MAX_EXPANSION_PAGES = 80;
export const MAX_EXPANSION_PRODUCTS = 5_000;
export const MAX_EXPANSIONS = 2_000;
export const UNMATCHED_IMAGE_BATCH = 1;
export const DEFAULT_PACE = "fast";
export function normalizePace(name) {
  if (name === "between" || name === "medium" || name === "slow") {
    return "between";
  }
  return "fast";
}
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
  between: {
    readMin: 1_800,
    readMax: 6_000,
    pageMin: 4_500,
    pageMax: 12_000,
    setMin: 9_000,
    setMax: 21_000,
    thinkMin: 900,
    thinkMax: 3_400,
    settleMin: 2_200,
    settleMax: 6_800,
    breakEveryMin: 5,
    breakEveryMax: 10,
    breakMin: 25_000,
    breakMax: 68_000,
    hesitateChance: 0.12,
    hesitateMin: 4_500,
    hesitateMax: 18_000,
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
  "saveUnmatchedImage",
];
