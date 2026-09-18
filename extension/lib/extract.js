import { PARSER_VERSION } from "./constants.js";
import { extractPrices, hasChallenge, hasEmptyState } from "./parse.js";
import { classifyUrl } from "./url.js";

export function classifyPage({
  url,
  title = "",
  prices = [],
  articleRowCount = 0,
  emptyState = false,
  challenge = false,
}) {
  const kind = classifyUrl(url);
  if (challenge || kind === "login" || kind === "challenge") {
    return { outcome: "challenge" };
  }
  if (kind === "search" || kind === "other" || kind === "invalid") {
    return { outcome: "wrong_product" };
  }
  if (kind === "pokemontcg") {
    return { outcome: "loading" };
  }
  if (prices.length) {
    return { outcome: "offers", prices };
  }
  if (emptyState) {
    return { outcome: "empty", prices: [] };
  }
  if (articleRowCount > 0) {
    return { outcome: "unrecognized" };
  }
  return { outcome: "unrecognized" };
}

export function collectPage(root, href, title) {
  const prices = extractPrices(root);
  const articleRowCount = root.querySelectorAll?.(".article-row, tr.article")?.length ?? 0;
  const classified = classifyPage({
    url: href,
    title,
    prices,
    articleRowCount,
    emptyState: hasEmptyState(root),
    challenge: hasChallenge(root, href, title),
  });
  return {
    ...classified,
    url: href,
    title,
    parserVersion: PARSER_VERSION,
    sampledOfferCount: classified.prices?.length || 0,
    observedAt: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
  };
}

export async function extractJob(requestId, jobId, root = document, href = window.location.href, title = document.title) {
  const result = await waitForPage(root, href, title);
  return {
    type: "extract-result",
    requestId,
    jobId,
    ...result,
    url: href,
  };
}

export function waitForPage(root, href, title, { timeoutMs = 15_000, intervalMs = 300 } = {}) {
  return new Promise((resolve) => {
    const started = Date.now();
    let observer;
    const finish = (result) => {
      observer?.disconnect();
      resolve(result);
    };
    const sample = () => {
      const result = collectPage(root, href, title);
      if (result.outcome !== "unrecognized" || Date.now() - started >= timeoutMs) {
        finish(result);
        return true;
      }
      return false;
    };
    if (sample()) {
      return;
    }
    observer = root.defaultView
      ? new root.defaultView.MutationObserver(() => {
          sample();
        })
      : null;
    observer?.observe(root.documentElement || root, { childList: true, subtree: true });
    const tick = () => {
      if (sample()) {
        return;
      }
      setTimeout(tick, intervalMs);
    };
    setTimeout(tick, intervalMs);
  });
}
