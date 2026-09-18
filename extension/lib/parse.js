export function parseAmount(text) {
  const source = String(text || "").replace(/\s/g, "");
  const european = source.match(/(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})/);
  const us = source.match(/(\d{1,3}(?:,\d{3})+\.\d{2}|\d+\.\d{2})/);
  let raw = null;
  if (european && us) {
    raw = source.lastIndexOf(",") > source.lastIndexOf(".") ? european[1] : us[1];
  } else if (european) {
    raw = european[1];
  } else if (us) {
    raw = us[1];
  }
  if (!raw) {
    return null;
  }
  if (raw.includes(".") && raw.includes(",")) {
    if (raw.lastIndexOf(",") > raw.lastIndexOf(".")) {
      raw = raw.replace(/\./g, "").replace(",", ".");
    } else {
      raw = raw.replace(/,/g, "");
    }
  } else if (/,\d{2}$/.test(raw)) {
    raw = raw.replace(",", ".");
  } else {
    raw = raw.replace(/,/g, "");
  }
  const amount = Number.parseFloat(raw);
  if (!Number.isFinite(amount) || amount <= 0) {
    return null;
  }
  return Math.round(amount * 100) / 100;
}

const CONDITION_RE = /^(NM|M|EX|GD|LP|PL|PO|SS|MT|Near Mint|Excellent)$/i;

function conditionLabel(row) {
  const nodes = row.querySelectorAll?.(".article-condition, [class*='condition'], .badge") ?? [];
  for (const node of nodes) {
    const text = (node.textContent || "").trim().replace(/\s+/g, " ");
    if (text && CONDITION_RE.test(text.split(/\s/)[0] || text)) {
      return text.split(/\s/)[0];
    }
  }
  const fallback = (row.querySelector?.(".article-condition")?.textContent || "").trim();
  return fallback;
}

function offerNode(row) {
  const offer = row.querySelector?.(".col-offer, .price-container, [class*='col-offer']");
  if (!offer) {
    return null;
  }
  if (offer.closest?.(".mobile-offer-container")) {
    return null;
  }
  return offer;
}

function extractRowPrices(root) {
  const prices = [];
  const seen = new Set();
  const rows = root.querySelectorAll?.(".article-row, tr.article") ?? [];
  for (const row of rows) {
    const label = conditionLabel(row);
    const offer = offerNode(row);
    if (!offer) {
      continue;
    }
    const amount = parseAmount(offer.textContent || "");
    if (!label || amount == null) {
      continue;
    }
    const key = `${label}-${amount}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    prices.push({ label, amount, currency: "EUR" });
    if (prices.length >= 3) {
      break;
    }
  }
  return prices;
}

export function extractGuidePrices(root) {
  const text = `${root.body?.innerText || root.textContent || ""}`;
  const specs = [
    { re: /(?:^|\n)\s*From\s+([\d.,]+)\s*€/i, label: "From" },
    { re: /Price Trend\s+([\d.,]+)\s*€/i, label: "Trend" },
    { re: /7-days? average price\s+([\d.,]+)\s*€/i, label: "7-day" },
  ];
  const prices = [];
  for (const spec of specs) {
    const match = text.match(spec.re);
    if (!match) {
      continue;
    }
    const amount = parseAmount(`${match[1]} €`);
    if (amount == null) {
      continue;
    }
    prices.push({ label: spec.label, amount, currency: "EUR" });
  }
  return prices;
}

export function extractPrices(root) {
  const rows = extractRowPrices(root);
  return rows.length ? rows : extractGuidePrices(root);
}

export function hasEmptyState(root) {
  const text = `${root.body?.innerText || root.textContent || ""}`.toLowerCase();
  if (root.querySelector?.("[data-test-empty-articles], .noArticles, .no-articles")) {
    return true;
  }
  return (
    text.includes("there are currently no articles") ||
    text.includes("no articles available") ||
    text.includes("there are no articles")
  );
}

export function challengeTitle(title) {
  const text = String(title || "").toLowerCase();
  return (
    text.includes("just a moment") ||
    text.includes("einen moment") ||
    text.includes("attention required") ||
    text.includes("checking your browser") ||
    text.includes("verify you are human") ||
    (text.includes("cloudflare") && !text.includes("cardmarket"))
  );
}

export function hasChallenge(root, url = "", title = "") {
  if (root.querySelector?.("#challenge-form, .cf-turnstile, #cf-challenge, input[name='cf-turnstile-response']")) {
    return true;
  }
  return challengeTitle(title);
}
