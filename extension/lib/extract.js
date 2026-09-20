import { PARSER_VERSION } from "./constants.js";
import { extractPrices, hasChallenge, hasEmptyState } from "./parse.js";
import { classifyUrl } from "./url.js";

const LISTING_IMAGE_SELECTOR = [
  "img.is-front",
  ".card-image img.is-front",
  "#image img.is-front",
  "#image img",
  ".card-image img",
  "img[itemprop='image']",
  ".is-product-image img",
].join(", ");

export function listingImageNode(root) {
  const picked = mainListingImage(root);
  return picked?.img || root.querySelector?.(LISTING_IMAGE_SELECTOR) || null;
}

export function listingImageNodes(root) {
  if (typeof root.querySelectorAll === "function") {
    return Array.from(root.querySelectorAll(LISTING_IMAGE_SELECTOR) || []);
  }
  const one = root.querySelector?.(LISTING_IMAGE_SELECTOR);
  return one ? [one] : [];
}

export function isCardmarketListingImageUrl(src) {
  try {
    const parsed = new URL(src);
    const host = parsed.hostname.toLowerCase();
    const path = parsed.pathname.toLowerCase();
    if (
      host === "product-images.s3.cardmarket.com" ||
      host.endsWith(".product-images.s3.cardmarket.com")
    ) {
      return true;
    }
    if (
      (host === "static.cardmarket.com" || host.endsWith(".static.cardmarket.com")) &&
      /\.(jpe?g|webp|png)$/.test(path) &&
      !/logo|favicon|icon|placeholder|sprite/.test(path)
    ) {
      return true;
    }
    return false;
  } catch {
    return false;
  }
}

export function imageSrc(img) {
  return String(img?.currentSrc || img?.src || img?.getAttribute?.("src") || "");
}

export function mainListingImage(root) {
  let best = null;
  for (const img of listingImageNodes(root)) {
    const src = imageSrc(img);
    if (!src || !isCardmarketListingImageUrl(src)) {
      continue;
    }
    const width = Number(img.naturalWidth || img.width || 0);
    const height = Number(img.naturalHeight || img.height || 0);
    const area = width * height;
    const className = String(img.className || "");
    const isFront = className.includes("is-front") || Boolean(img.classList?.contains?.("is-front"));
    const inMain = Boolean(img.closest?.("#image, .card-image, .is-product-image, .image"));
    const ready = Boolean((img.complete !== false) && width >= 80);
    const score = (inMain ? 1_000_000_000 : 0) + (isFront ? 100_000_000 : 0) + area;
    if (!best || score > best.score) {
      best = { img, src, ready, score };
    }
  }
  return best;
}

export function productImageSrc(root) {
  const main = mainListingImage(root);
  if (main?.src) {
    return main.src;
  }
  const og = root.querySelector?.('meta[property="og:image"]');
  return String(og?.content || og?.getAttribute?.("content") || "");
}

export async function captureProductImage(root = document) {
  const src = productImageSrc(root);
  const img = listingImageNode(root);
  if (img && img.complete && img.naturalWidth) {
    try {
      const canvas = root.defaultView?.document?.createElement?.("canvas") || document.createElement("canvas");
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0);
      const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
      return { dataUrl, src, mime: "image/jpeg" };
    } catch {
      /* tainted canvas — fetch the src in the helper instead */
    }
  }
  return { dataUrl: "", src, mime: "" };
}

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
