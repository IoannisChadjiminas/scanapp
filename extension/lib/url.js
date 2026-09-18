const PRODUCT_PATH = /^\/[a-z]{2}\/Pokemon\/Products\/Singles\/[^/]+\/[^/]+$/i;
const EXPANSION_PATH = /^\/[a-z]{2}\/Pokemon\/Products\/Singles\/[^/]+$/i;
const SINGLES_ROOT = /^\/[a-z]{2}\/Pokemon\/Products\/Singles$/i;

export function normalizeUrl(url) {
  try {
    const parsed = new URL(url);
    parsed.hash = "";
    parsed.search = "";
    parsed.pathname = parsed.pathname.replace(/\/$/, "");
    return parsed.toString();
  } catch {
    return url || "";
  }
}

export function hostOf(url) {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return "";
  }
}

export function classifyUrl(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return "invalid";
  }
  if (parsed.protocol !== "https:") {
    return "invalid";
  }
  const host = parsed.hostname.toLowerCase();
  const path = parsed.pathname.replace(/\/$/, "");
  if (host === "prices.pokemontcg.io" || host === "www.prices.pokemontcg.io") {
    return path.toLowerCase().includes("/cardmarket/") ? "pokemontcg" : "invalid";
  }
  if (host !== "www.cardmarket.com" && host !== "cardmarket.com") {
    return "invalid";
  }
  const lowered = path.toLowerCase();
  if (lowered.includes("/login") || lowered.endsWith("/signin")) {
    return "login";
  }
  if (PRODUCT_PATH.test(path)) {
    return "product";
  }
  if (EXPANSION_PATH.test(path)) {
    return "expansion";
  }
  if (SINGLES_ROOT.test(path)) {
    const expansionId = parsed.searchParams.get("idExpansion");
    if (expansionId && !/^(all|-1|0)?$/i.test(expansionId)) {
      return "expansion";
    }
    return "singles-index";
  }
  if (lowered.includes("/cdn-cgi/") || lowered.includes("/captcha")) {
    return "challenge";
  }
  if (lowered.includes("/products/search") || lowered.endsWith("/cards")) {
    return "search";
  }
  return "other";
}

export function productIdentity(url) {
  const kind = classifyUrl(url);
  if (kind === "pokemontcg") {
    const pid = String(url || "").replace(/\/$/, "").split("/").pop();
    return pid ? `pokemontcg:${pid}` : null;
  }
  if (kind !== "product") {
    return null;
  }
  const path = new URL(url).pathname.replace(/\/$/, "");
  const slug = path.split("/").pop() || "";
    const match = slug.match(/-([A-Za-z]+)(\d+)$/);
  if (!match) {
    const bits = path.split("/").filter(Boolean);
    return `path:${bits.at(-2)?.toLowerCase()}/${bits.at(-1)?.toLowerCase()}`;
  }
  let letters = match[1];
  let digits = match[2];
  if (digits.length > 3) {
    letters += digits.slice(0, -3);
    digits = digits.slice(-3);
  }
  return `singles:${letters.toLowerCase()}${digits.replace(/^0+/, "") || "0"}`;
}

export function identitiesCompatible(expected, actual) {
  if (!expected || !actual) {
    return false;
  }
  if (String(expected).startsWith("pokemontcg:")) {
    return String(actual).startsWith("singles:") || String(actual).startsWith("path:");
  }
  return expected === actual;
}

export function finalUrlAllowed(jobUrl, finalUrl) {
  if (classifyUrl(finalUrl) !== "product") {
    return false;
  }
  return identitiesCompatible(productIdentity(jobUrl), productIdentity(finalUrl));
}

export function listingFilters(url) {
  try {
    const params = new URL(url).searchParams;
    const filters = {};
    for (const key of ["language", "minCondition", "sellerCountry", "isReverseHolo"]) {
      const value = params.get(key);
      if (value) {
        filters[key] = value;
      }
    }
    return filters;
  } catch {
    return {};
  }
}
