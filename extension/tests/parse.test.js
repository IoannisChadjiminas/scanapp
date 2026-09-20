import assert from "node:assert/strict";
import test from "node:test";

import { parseAmount, extractPrices, hasChallenge } from "../lib/parse.js";
import { classifyPage, isCardmarketListingImageUrl, productImageSrc } from "../lib/extract.js";

test("parses supported Cardmarket amounts and rejects invalid ones", () => {
  assert.equal(parseAmount("1,50 €"), 1.5);
  assert.equal(parseAmount("0,10 €"), 0.1);
  assert.equal(parseAmount("12.50"), 12.5);
  assert.equal(parseAmount("1.234,56"), 1234.56);
  assert.equal(parseAmount("1,234.56"), 1234.56);
  assert.equal(parseAmount("free"), null);
  assert.equal(parseAmount("0,00"), null);
});

test("reads guide prices from the product info box", () => {
  const root = {
    body: {
      innerText:
        "From\n0,10 €\nPrice Trend\n1,48 €\n30-days average price\n1,95 €\n7-days average price\n1,69 €",
    },
    querySelectorAll: () => [],
  };
  assert.deepEqual(extractPrices(root), [
    { label: "From", amount: 0.1, currency: "EUR" },
    { label: "Trend", amount: 1.48, currency: "EUR" },
    { label: "7-day", amount: 1.69, currency: "EUR" },
  ]);
});

test("missing selectors are not treated as no offers", () => {
  assert.equal(classifyPage({ url: "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102" }).outcome, "unrecognized");
  assert.equal(
    classifyPage({
      url: "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102",
      emptyState: true,
    }).outcome,
    "empty",
  );
  assert.equal(
    classifyPage({
      url: "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102",
      articleRowCount: 4,
    }).outcome,
    "unrecognized",
  );
  assert.equal(
    classifyPage({
      url: "https://www.cardmarket.com/en/Login",
      challenge: true,
    }).outcome,
    "challenge",
  );
});

test("reads the Cardmarket product image from og:image", () => {
  const root = {
    querySelector(sel) {
      if (sel === 'meta[property="og:image"]') {
        return { content: "https://static.cardmarket.com/img/gengar.jpg" };
      }
      return null;
    },
  };
  assert.equal(productImageSrc(root), "https://static.cardmarket.com/img/gengar.jpg");
});

test("reads the visible Cardmarket card image from img.is-front", () => {
  const src = "https://product-images.s3.cardmarket.com/51/MEW/733658/733658.jpg";
  const img = {
    currentSrc: src,
    src,
    naturalWidth: 300,
    width: 300,
    naturalHeight: 420,
    height: 420,
    complete: true,
    className: "is-front",
    classList: { contains: (name) => name === "is-front" },
    getAttribute: () => src,
    closest: (sel) => (String(sel).includes("#image") ? {} : null),
  };
  const root = {
    querySelector(sel) {
      if (String(sel).includes("img.is-front") || String(sel).includes(".card-image img") || String(sel).includes("#image img")) {
        return img;
      }
      if (sel === 'meta[property="og:image"]') {
        return { content: "https://static.cardmarket.com/img/ignored.jpg" };
      }
      return null;
    },
  };
  assert.equal(productImageSrc(root), src);
});

test("does not pick a previous-product gallery thumb", () => {
  const neighbor = "https://product-images.s3.cardmarket.com/51/SV5s/890176/890176.jpg";
  const main = "https://product-images.s3.cardmarket.com/51/SV5s/890177/890177.jpg";
  const page = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Ace-Paradox/Flutter-Mane-SV5s154";
  const prev = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Ace-Paradox/Cutiefly-SV5s153";
  const thumbImg = {
    currentSrc: neighbor,
    src: neighbor,
    naturalWidth: 255,
    naturalHeight: 361,
    width: 255,
    height: 361,
    complete: true,
    className: "is-front",
    classList: { contains: (name) => name === "is-front" },
    closest: (sel) =>
      String(sel).includes("a[href]")
        ? { href: prev, getAttribute: (name) => (name === "href" ? prev : "") }
        : null,
    getAttribute: () => neighbor,
  };
  const mainImg = {
    currentSrc: main,
    src: main,
    naturalWidth: 255,
    naturalHeight: 361,
    width: 255,
    height: 361,
    complete: true,
    className: "is-front",
    classList: { contains: (name) => name === "is-front" },
    closest: (sel) => (String(sel).includes("#image") ? {} : null),
    getAttribute: () => main,
  };
  const root = {
    location: { href: page },
    querySelector(sel) {
      if (String(sel).includes("og:image")) {
        return { content: main, getAttribute: (name) => (name === "content" ? main : "") };
      }
      if (String(sel).includes("idProduct")) {
        return { value: "890177", getAttribute: () => "890177" };
      }
      return thumbImg;
    },
    querySelectorAll: () => [thumbImg, mainImg],
  };
  assert.equal(productImageSrc(root), main);
});

test("prefers the main product image over a smaller gallery thumb", () => {
  const thumb = "https://product-images.s3.cardmarket.com/51/s8a/577378/577378.jpg";
  const main = "https://product-images.s3.cardmarket.com/51/s8a/577379/577379.jpg";
  const thumbImg = {
    currentSrc: thumb,
    src: thumb,
    naturalWidth: 40,
    naturalHeight: 40,
    width: 40,
    height: 40,
    complete: true,
    className: "is-front",
    classList: { contains: (name) => name === "is-front" },
    closest: () => null,
    getAttribute: () => thumb,
  };
  const mainImg = {
    currentSrc: main,
    src: main,
    naturalWidth: 300,
    naturalHeight: 420,
    width: 300,
    height: 420,
    complete: true,
    className: "is-front",
    classList: { contains: (name) => name === "is-front" },
    closest: (sel) => (String(sel).includes("#image") ? {} : null),
    getAttribute: () => main,
  };
  const root = {
    querySelectorAll() {
      return [thumbImg, mainImg];
    },
    querySelector() {
      return thumbImg;
    },
  };
  assert.equal(productImageSrc(root), main);
});

test("detects a Turnstile iframe as Cloudflare", () => {
  const root = {
    querySelector(sel) {
      if (String(sel).includes("challenges.cloudflare.com") || String(sel).includes("turnstile")) {
        return { src: "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/turnstile" };
      }
      return null;
    },
  };
  assert.equal(hasChallenge(root, "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Abra-V1-MEW063", "Abra"), true);
});

test("accepts Cardmarket listing image hosts and rejects logos", () => {
  assert.equal(
    isCardmarketListingImageUrl("https://product-images.s3.cardmarket.com/51/10M/566543/566543.jpg"),
    true,
  );
  assert.equal(isCardmarketListingImageUrl("https://static.cardmarket.com/img/cardmarket-logo.png"), false);
  assert.equal(isCardmarketListingImageUrl("https://example.com/566543.jpg"), false);
});
