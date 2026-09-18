function scanappParseAmount(text) {
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

function scanappCollectCardmarket() {
  const href = window.location.href;
  const title = document.title || "";
  const root = document;
  const text = `${root.body?.innerText || root.textContent || ""}`;
  const haystack = `${href} ${title} ${text}`.toLowerCase();
  const challenge =
    Boolean(root.querySelector("#challenge-form, .cf-turnstile, #cf-challenge, input[name='cf-turnstile-response']")) ||
    haystack.includes("just a moment") ||
    haystack.includes("attention required") ||
    haystack.includes("cloudflare");
  let kind = "other";
  try {
    const parsed = new URL(href);
    const host = parsed.hostname.toLowerCase();
    const path = parsed.pathname.replace(/\/$/, "");
    const lowered = path.toLowerCase();
    if (host === "prices.pokemontcg.io" || host === "www.prices.pokemontcg.io") {
      kind = lowered.includes("/cardmarket/") ? "pokemontcg" : "invalid";
    } else if (host !== "www.cardmarket.com" && host !== "cardmarket.com") {
      kind = "invalid";
    } else if (lowered.includes("/login") || lowered.endsWith("/signin")) {
      kind = "login";
    } else if (lowered.includes("challenge") || lowered.includes("/captcha")) {
      kind = "challenge";
    } else if (lowered.includes("/products/search") || lowered.endsWith("/cards")) {
      kind = "search";
    } else if (/^\/[a-z]{2}\/Pokemon\/Products\/Singles\/[^/]+\/[^/]+$/i.test(path)) {
      kind = "product";
    }
  } catch {
    kind = "invalid";
  }

  const conditionRe = /^(NM|M|EX|GD|LP|PL|PO|SS|MT|Near Mint|Excellent)$/i;
  const prices = [];
  const seen = new Set();
  const rows = root.querySelectorAll(".article-row, tr.article");
  for (const row of rows) {
    let label = "";
    const nodes = row.querySelectorAll(".article-condition, [class*='condition'], .badge");
    for (const node of nodes) {
      const value = (node.textContent || "").trim().replace(/\s+/g, " ");
      if (value && conditionRe.test(value.split(/\s/)[0] || value)) {
        label = value.split(/\s/)[0];
        break;
      }
    }
    if (!label) {
      label = (row.querySelector(".article-condition")?.textContent || "").trim();
    }
    const offer = row.querySelector(".col-offer, .price-container, [class*='col-offer']");
    if (!offer || offer.closest(".mobile-offer-container")) {
      continue;
    }
    const amount = scanappParseAmount(offer.textContent || "");
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
  if (!prices.length) {
    const specs = [
      { re: /(?:^|\n)\s*From\s+([\d.,]+)\s*€/i, label: "From" },
      { re: /Price Trend\s+([\d.,]+)\s*€/i, label: "Trend" },
      { re: /7-days? average price\s+([\d.,]+)\s*€/i, label: "7-day" },
    ];
    for (const spec of specs) {
      const match = text.match(spec.re);
      if (!match) {
        continue;
      }
      const amount = scanappParseAmount(`${match[1]} €`);
      if (amount == null) {
        continue;
      }
      prices.push({ label: spec.label, amount, currency: "EUR" });
    }
  }

  let outcome = "unrecognized";
  if (challenge || kind === "login" || kind === "challenge") {
    outcome = "challenge";
  } else if (kind === "search" || kind === "other" || kind === "invalid") {
    outcome = "wrong_product";
  } else if (kind === "pokemontcg") {
    outcome = "loading";
  } else if (prices.length) {
    outcome = "offers";
  } else if (
    root.querySelector("[data-test-empty-articles], .noArticles, .no-articles") ||
    text.toLowerCase().includes("there are currently no articles") ||
    text.toLowerCase().includes("no articles available") ||
    text.toLowerCase().includes("there are no articles")
  ) {
    outcome = "empty";
  }

  return {
    outcome,
    prices,
    url: href,
    title,
    parserVersion: "offers-v1",
    sampledOfferCount: prices.length,
    observedAt: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
  };
}

scanappCollectCardmarket();
