import { classifyUrl, normalizeUrl } from "./url.js";

export function asProductUrl(href, pageUrl) {
  if (!href) {
    return null;
  }
  try {
    const absolute = new URL(href, pageUrl).toString();
    return classifyUrl(absolute) === "product" ? normalizeUrl(absolute) : null;
  } catch {
    return null;
  }
}

export function nextExpansionPage(candidates, pageUrl) {
  let currentSite = 1;
  try {
    currentSite = Number(new URL(pageUrl).searchParams.get("site") || "1") || 1;
  } catch {
    currentSite = 1;
  }
  for (const item of candidates || []) {
    const href = item?.href || "";
    const rel = String(item?.rel || "").toLowerCase();
    const text = String(item?.text || "").trim();
    if (!href) {
      continue;
    }
    let absolute;
    try {
      absolute = new URL(href, pageUrl);
    } catch {
      continue;
    }
    if (rel === "next") {
      return absolute.toString();
    }
    const site = Number(absolute.searchParams.get("site") || "");
    if (site === currentSite + 1) {
      return absolute.toString();
    }
    if (/^(next|»|>)$/i.test(text) && site > currentSite) {
      return absolute.toString();
    }
  }
  return null;
}

export function collectExpansionSnapshot(root, pageUrl) {
  const products = [];
  const seen = new Set();
  const anchors = root?.querySelectorAll?.("a[href]") || [];
  for (const node of anchors) {
    const href = node.href || node.getAttribute?.("href") || "";
    const url = asProductUrl(href, pageUrl);
    if (!url || seen.has(url)) {
      continue;
    }
    seen.add(url);
    products.push({
      url,
      name: String(node.textContent || "")
        .trim()
        .replace(/\s+/g, " "),
    });
  }
  const candidates = [];
  for (const node of anchors) {
    candidates.push({
      href: node.href || node.getAttribute?.("href") || "",
      rel: node.getAttribute?.("rel") || "",
      text: String(node.textContent || "").trim(),
    });
  }
  return {
    pageUrl,
    products,
    nextPage: nextExpansionPage(candidates, pageUrl),
  };
}
