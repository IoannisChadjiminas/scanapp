import { hasChallenge } from "./parse.js";
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

function skipExpansionLabel(text, value) {
  const label = String(text || "").trim().toLowerCase();
  const raw = String(value || "").trim().toLowerCase();
  return (!label && !raw) || label === "all" || raw === "all" || raw === "-1" || raw === "0";
}

export function expansionStartUrl(value, text, pageUrl) {
  let origin;
  try {
    origin = new URL(pageUrl);
  } catch {
    return null;
  }
  const locale = origin.pathname.split("/").filter(Boolean)[0] || "en";
  const raw = String(value || "").trim();
  const label = String(text || "").trim();
  if (skipExpansionLabel(label, raw) || !/^\d+$/.test(raw)) {
    return null;
  }
  const url = new URL(`/${locale}/Pokemon/Products/Singles`, origin.origin);
  url.searchParams.set("idExpansion", raw);
  return url.toString();
}

function expansionKey(url) {
  try {
    const parsed = new URL(url);
    parsed.hash = "";
    parsed.pathname = parsed.pathname.replace(/\/$/, "");
    parsed.searchParams.delete("site");
    return `${parsed.pathname}?${parsed.searchParams.get("idExpansion") || ""}`;
  } catch {
    return String(url || "");
  }
}

function isExpansionSelect(node) {
  const ident = [
    node?.name,
    node?.id,
    node?.getAttribute?.("name"),
    node?.getAttribute?.("id"),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return ident.includes("xpansion");
}

export function collectExpansionTargets(root, pageUrl) {
  const found = new Map();
  const add = (url, name, id = "") => {
    if (!url || classifyUrl(url) !== "expansion") {
      return;
    }
    const key = expansionKey(url);
    if (!found.has(key)) {
      found.set(key, { url, name: String(name || "").trim(), id: String(id || "") });
    }
  };
  const selects = root?.querySelectorAll?.("select") || [];
  for (const select of selects) {
    if (!isExpansionSelect(select)) {
      continue;
    }
    const options = Array.from(select.options || select.querySelectorAll?.("option") || []);
    for (const opt of options) {
      const value = String(opt.value || opt.getAttribute?.("value") || "").trim();
      const name = String(opt.textContent || opt.label || opt.getAttribute?.("label") || "")
        .trim()
        .replace(/\s+/g, " ");
      const built = expansionStartUrl(value, name, pageUrl);
      if (built) {
        add(built, name, value);
      }
    }
  }
  const nodes = root?.querySelectorAll?.('[role="option"], [data-expansion-id]') || [];
  for (const node of nodes) {
    const value = String(
      node.getAttribute?.("data-value") ||
        node.getAttribute?.("data-expansion-id") ||
        node.value ||
        "",
    ).trim();
    const name = String(node.textContent || "").trim().replace(/\s+/g, " ");
    const built = expansionStartUrl(value, name, pageUrl);
    if (built) {
      add(built, name, value);
    }
  }
  return [...found.values()];
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

export function collectExpansionSnapshot(root, pageUrl, title = "") {
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
    expansions: collectExpansionTargets(root, pageUrl),
    challenge: hasChallenge(root, pageUrl, title),
  };
}
