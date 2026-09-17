function parseAmount(text) {
  const match = String(text || "").replace(/\s/g, " ").match(
    /(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+\.\d{2})/,
  );
  if (!match) {
    return null;
  }
  let raw = match[1];
  if (raw.includes(".") && raw.includes(",")) {
    raw = raw.replace(/\./g, "").replace(",", ".");
  } else if (raw.includes(",")) {
    raw = raw.replace(",", ".");
  }
  const amount = Number.parseFloat(raw);
  return Number.isFinite(amount) ? amount : null;
}

function extractPrices() {
  const prices = [];
  const seen = new Set();
  for (const row of document.querySelectorAll(".article-row")) {
    const label = (
      row.querySelector(".article-condition")?.textContent || ""
    ).trim();
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

function waitForRows() {
  return new Promise((resolve) => {
    let attempts = 0;
    const tick = () => {
      const prices = extractPrices();
      if (prices.length || attempts >= 20) {
        resolve(prices);
        return;
      }
      attempts += 1;
      window.setTimeout(tick, 400);
    };
    tick();
  });
}

waitForRows().then((prices) => {
  chrome.runtime.sendMessage({
    type: "cardmarket-offers",
    url: window.location.href,
    prices,
  });
});
