function scanappCollectExpansion() {
  const pageUrl = window.location.href;
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
  return { pageUrl, products, nextPage };
}

scanappCollectExpansion();
