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

export function extractPrices(root) {
  const prices = [];
  const seen = new Set();
  const rows = root.querySelectorAll?.(".article-row") ?? [];
  for (const row of rows) {
    const label = (row.querySelector(".article-condition")?.textContent || "").trim();
    const offer = row.querySelector(".col-offer");
    if (!offer || offer.closest(".mobile-offer-container")) {
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

export function hasChallenge(root, url = "", title = "") {
  const haystack = `${url} ${title} ${root.body?.innerText || ""}`.toLowerCase();
  if (root.querySelector?.("#challenge-form, .cf-turnstile, #cf-challenge, input[name='cf-turnstile-response']")) {
    return true;
  }
  return haystack.includes("just a moment") || haystack.includes("attention required") || haystack.includes("cloudflare");
}
