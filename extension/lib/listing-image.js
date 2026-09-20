const LISTING_IMAGE_SELECTOR = [
  "img.is-front",
  "#image img",
  ".card-image img",
  ".is-product-image img",
  ".product-image img",
  ".image-container img",
  "img[itemprop='image']",
].join(", ");

const MAIN_IMAGE_SELECTOR = "#image, .card-image, .is-product-image, .product-image, .image-container, .image";

export function listingSrcOk(src) {
  try {
    const parsed = new URL(src, "https://www.cardmarket.com/");
    const host = parsed.hostname.toLowerCase();
    const path = parsed.pathname.toLowerCase();
    if (/logo|favicon|icon|placeholder|sprite|notavailable/i.test(src)) {
      return false;
    }
    if (host === "product-images.s3.cardmarket.com" || host.endsWith(".product-images.s3.cardmarket.com")) {
      return true;
    }
    return (
      (host === "static.cardmarket.com" || host.endsWith(".static.cardmarket.com")) &&
      /\.(jpe?g|webp|png)$/.test(path)
    );
  } catch {
    return false;
  }
}

export function s3ProductId(src) {
  const match = String(src).match(/\/(\d+)\/\1\.(?:jpe?g|png|webp)(?:\?|$)/i);
  return match ? match[1] : "";
}

function attr(node, name) {
  if (!node) {
    return "";
  }
  if (typeof node.getAttribute === "function") {
    return String(node.getAttribute(name) || "");
  }
  return String(node[name] || "");
}

function queryOne(root, selector) {
  return root?.querySelector?.(selector) || null;
}

function queryAll(root, selector) {
  if (typeof root?.querySelectorAll === "function") {
    return Array.from(root.querySelectorAll(selector) || []);
  }
  const one = queryOne(root, selector);
  return one ? [one] : [];
}

export function pageHref(root, fallback = "") {
  return String(root?.location?.href || fallback || "");
}

function digitsId(raw) {
  const text = String(raw || "").trim();
  return /^\d{4,}$/.test(text) ? text : "";
}

export function pageProductId(root) {
  const nodes = [
    queryOne(root, 'input[name="idProduct"]'),
    queryOne(root, "input#idProduct"),
    queryOne(root, "[data-id-product]"),
    queryOne(root, "[data-product-id]"),
    queryOne(root, "[data-idproduct]"),
    queryOne(root, 'meta[property="product:retailer_item_id"]'),
    queryOne(root, 'meta[itemprop="sku"]'),
    queryOne(root, 'meta[itemprop="productID"]'),
  ];
  for (const node of nodes) {
    const raw =
      node?.value ||
      node?.content ||
      attr(node, "content") ||
      attr(node, "data-id-product") ||
      attr(node, "data-product-id") ||
      attr(node, "data-idproduct") ||
      "";
    const id = digitsId(raw);
    if (id) {
      return id;
    }
  }
  for (const script of queryAll(root, 'script[type="application/ld+json"]')) {
    try {
      const parsed = JSON.parse(script.textContent || script.innerText || "null");
      const items = Array.isArray(parsed) ? parsed : [parsed];
      for (const item of items) {
        const id = digitsId(item?.sku || item?.productID || item?.productId || "");
        if (id) {
          return id;
        }
      }
    } catch {
      /* ignore invalid JSON-LD */
    }
  }
  const html = String(root?.documentElement?.innerHTML || "").slice(0, 250000);
  const patterns = [
    /name=["']idProduct["'][^>]*value=["'](\d{4,})/i,
    /value=["'](\d{4,})["'][^>]*name=["']idProduct["']/i,
    /["']idProduct["']\s*[:=]\s*["']?(\d{4,})/,
    /[?&]idProduct=(\d{4,})/,
  ];
  for (const pattern of patterns) {
    const match = html.match(pattern);
    if (match) {
      return match[1];
    }
  }
  return "";
}

export function ogListingSrc(root) {
  const meta = queryOne(root, 'meta[property="og:image"]');
  const link = queryOne(root, 'link[rel="image_src"]');
  const src = String(meta?.content || attr(meta, "content") || link?.href || attr(link, "href") || "");
  return listingSrcOk(src) ? src : "";
}

function productPath(href, baseHref) {
  try {
    return new URL(href, baseHref || "https://www.cardmarket.com/").pathname.replace(/\/+$/, "").toLowerCase();
  } catch {
    return "";
  }
}

export function isOtherProductImage(img, href) {
  const anchor = img?.closest?.("a[href]");
  if (!anchor) {
    return false;
  }
  const link = String(anchor.href || attr(anchor, "href") || "");
  if (!/\/Products\//i.test(link)) {
    return false;
  }
  const pagePath = productPath(href);
  const linkPath = productPath(link, href);
  return Boolean(pagePath && linkPath && pagePath !== linkPath);
}

function imageSrc(img) {
  return String(img?.currentSrc || img?.src || attr(img, "src") || "");
}

export function pickListingImage(root, href = "") {
  const page = pageHref(root, href);
  const productId = pageProductId(root);
  const og = ogListingSrc(root);
  const images = [];
  for (const img of queryAll(root, LISTING_IMAGE_SELECTOR)) {
    const src = imageSrc(img);
    if (!src || !listingSrcOk(src)) {
      continue;
    }
    const width = Number(img.naturalWidth || img.width || 0);
    const height = Number(img.naturalHeight || img.height || 0);
    const isFront = Boolean(img.classList?.contains?.("is-front") || String(img.className || "").includes("is-front"));
    const inMain = Boolean(img.closest?.(MAIN_IMAGE_SELECTOR));
    const otherProduct = isOtherProductImage(img, page);
    images.push({
      img,
      src,
      width,
      height,
      isFront,
      inMain,
      otherProduct,
      ready: Boolean(img.complete !== false && width >= 80),
      productId: s3ProductId(src),
    });
  }

  const usable = images.filter((item) => !item.otherProduct);
  if (productId) {
    const matched = usable.filter((item) => item.productId === productId);
    const chosen = matched.find((item) => item.ready) || matched[0];
    if (chosen) {
      return {
        listingSrc: chosen.src,
        listingReady: Boolean(chosen.ready || chosen.inMain),
        hasListingImage: true,
        listingHow: "idProduct-img",
        idProduct: productId,
      };
    }
    if (s3ProductId(og) === productId) {
      return {
        listingSrc: og,
        listingReady: true,
        hasListingImage: true,
        listingHow: "idProduct-og",
        idProduct: productId,
      };
    }
  }
  let bestMain = null;
  let bestMainScore = -1;
  for (const item of usable) {
    if (!item.inMain) {
      continue;
    }
    const score = (item.isFront ? 100_000_000 : 0) + item.width * item.height;
    if (score > bestMainScore) {
      bestMain = item;
      bestMainScore = score;
    }
  }
  if (bestMain) {
    return {
      listingSrc: bestMain.src,
      listingReady: Boolean(bestMain.ready),
      hasListingImage: Boolean(bestMain.ready || bestMain.isFront),
      listingHow: "main-img",
      idProduct: productId,
    };
  }
  if (og) {
    return {
      listingSrc: og,
      listingReady: true,
      hasListingImage: true,
      listingHow: "og:image",
      idProduct: productId,
    };
  }
  if (usable.length === 1 && usable[0].ready) {
    return {
      listingSrc: usable[0].src,
      listingReady: true,
      hasListingImage: true,
      listingHow: "single-img",
      idProduct: productId,
    };
  }
  return {
    listingSrc: "",
    listingReady: false,
    hasListingImage: false,
    listingHow: "none",
    idProduct: productId,
  };
}
