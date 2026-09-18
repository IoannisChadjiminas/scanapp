function scanappCollectExpansion() {
  const pageUrl = window.location.href;
  const title = document.title || "";
  const challengeText = `${title} ${document.body?.innerText || ""}`.toLowerCase();
  const challenge = Boolean(
    document.querySelector(
      "#challenge-form, .cf-turnstile, #cf-challenge, input[name='cf-turnstile-response']",
    ),
  ) ||
    challengeText.includes("just a moment") ||
    challengeText.includes("attention required") ||
    challengeText.includes("cloudflare");
  const PRODUCT = /^\/[a-z]{2}\/Pokemon\/Products\/Singles\/[^/]+\/[^/]+$/i;
  const products = [];
  const seen = new Set();
  const anchors = document.querySelectorAll("a[href]");
  const candidates = [];
  for (const node of anchors) {
    const href = node.href || node.getAttribute("href") || "";
    candidates.push({
      href,
      rel: node.getAttribute("rel") || "",
      text: String(node.textContent || "").trim(),
    });
    let absolute;
    try {
      absolute = new URL(href, pageUrl);
    } catch {
      continue;
    }
    absolute.hash = "";
    absolute.search = "";
    absolute.pathname = absolute.pathname.replace(/\/$/, "");
    if (!PRODUCT.test(absolute.pathname)) {
      continue;
    }
    const url = absolute.toString();
    if (seen.has(url)) {
      continue;
    }
    seen.add(url);
    products.push({
      url,
      name: String(node.textContent || "").trim().replace(/\s+/g, " "),
    });
  }
  let currentSite = 1;
  try {
    currentSite = Number(new URL(pageUrl).searchParams.get("site") || "1") || 1;
  } catch {
    currentSite = 1;
  }
  let nextPage = null;
  for (const item of candidates) {
    if (!item.href) {
      continue;
    }
    let absolute;
    try {
      absolute = new URL(item.href, pageUrl);
    } catch {
      continue;
    }
    if (String(item.rel || "").toLowerCase() === "next") {
      nextPage = absolute.toString();
      break;
    }
    const site = Number(absolute.searchParams.get("site") || "");
    if (site === currentSite + 1) {
      nextPage = absolute.toString();
      break;
    }
  }
  const expansions = [];
  const expansionSeen = new Set();
  const origin = new URL(pageUrl);
  const locale = origin.pathname.split("/").filter(Boolean)[0] || "en";
  const addExpansion = (id, name) => {
    if (!/^\d+$/.test(String(id || ""))) {
      return;
    }
    const url = `${origin.origin}/${locale}/Pokemon/Products/Singles?idExpansion=${id}`;
    if (expansionSeen.has(url)) {
      return;
    }
    expansionSeen.add(url);
    expansions.push({ id: String(id), url, name: String(name || "").trim() });
  };
  const selects = document.querySelectorAll(
    'select[name="idExpansion"], select#idExpansion, select[name*="xpansion" i], select[id*="xpansion" i]',
  );
  for (const select of selects) {
    for (const opt of Array.from(select.options || [])) {
      const value = String(opt.value || "").trim();
      const name = String(opt.textContent || "").trim().replace(/\s+/g, " ");
      if (!value || value === "-1" || value === "0" || name.toLowerCase() === "all") {
        continue;
      }
      addExpansion(value, name);
    }
  }
  return { pageUrl, products, nextPage, expansions, challenge };
}

scanappCollectExpansion();
