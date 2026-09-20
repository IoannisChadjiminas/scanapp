import assert from "node:assert/strict";
import test from "node:test";

import { pickListingImage } from "../lib/listing-image.js";

const FLUTTER_PAGE =
  "https://www.cardmarket.com/en/Pokemon/Products/Singles/Ace-Paradox/Flutter-Mane-SV5s154";
const CUTIEFLY_PAGE =
  "https://www.cardmarket.com/en/Pokemon/Products/Singles/Ace-Paradox/Cutiefly-SV5s153";
const NEIGHBOR = "https://product-images.s3.cardmarket.com/51/SV5s/890176/890176.jpg";
const MAIN = "https://product-images.s3.cardmarket.com/51/SV5s/890177/890177.jpg";

function makeImg({ src, isFront = true, width = 300, height = 420, inMain = false, href = "" }) {
  return {
    src,
    currentSrc: src,
    naturalWidth: width,
    width,
    naturalHeight: height,
    height,
    complete: true,
    className: isFront ? "is-front" : "",
    classList: { contains: (name) => name === "is-front" && isFront },
    getAttribute: (name) => (name === "src" ? src : ""),
    closest(sel) {
      const parts = String(sel)
        .split(",")
        .map((part) => part.trim());
      if (parts.includes("a[href]") && href) {
        return { href, getAttribute: (name) => (name === "href" ? href : "") };
      }
      if (
        inMain &&
        parts.some((part) =>
          ["#image", ".card-image", ".is-product-image", ".product-image", ".image-container", ".image"].includes(
            part,
          ),
        )
      ) {
        return { id: "image" };
      }
      return null;
    },
  };
}

function makeDoc({ href, og = "", idProduct = "", images = [] }) {
  const nodes = images.map(makeImg);
  return {
    location: { href },
    documentElement: {
      innerHTML: idProduct ? `name="idProduct" value="${idProduct}"` : "",
    },
    querySelector(sel) {
      const selector = String(sel);
      if (selector.includes("og:image") && og) {
        return { content: og, getAttribute: (name) => (name === "content" ? og : "") };
      }
      if (selector.includes("image_src") && og) {
        return { href: og, getAttribute: (name) => (name === "href" ? og : "") };
      }
      if ((selector.includes("idProduct") || selector.includes("product-id")) && idProduct) {
        return {
          value: idProduct,
          getAttribute: (name) => (name.includes("id") || name.includes("product") ? idProduct : ""),
        };
      }
      if (selector.includes("img")) {
        return nodes[0] || null;
      }
      return null;
    },
    querySelectorAll(sel) {
      if (String(sel).includes("ld+json")) {
        return [];
      }
      if (String(sel).includes("img")) {
        return nodes;
      }
      return [];
    },
  };
}

test("does not store the previous gallery card from the first img.is-front", () => {
  const root = makeDoc({
    href: FLUTTER_PAGE,
    og: MAIN,
    idProduct: "890177",
    images: [
      { src: NEIGHBOR, width: 255, height: 361, href: CUTIEFLY_PAGE },
      { src: MAIN, width: 255, height: 361, inMain: true },
    ],
  });
  const picked = pickListingImage(root, FLUTTER_PAGE);
  assert.equal(picked.listingSrc, MAIN);
  assert.equal(picked.hasListingImage, true);
  assert.notEqual(picked.listingHow, "none");
});

test("uses og:image when the first is-front is a neighbor thumb", () => {
  const root = makeDoc({
    href: FLUTTER_PAGE,
    og: MAIN,
    images: [{ src: NEIGHBOR, width: 40, height: 56, href: CUTIEFLY_PAGE }],
  });
  assert.equal(pickListingImage(root, FLUTTER_PAGE).listingSrc, MAIN);
});

test("matches the S3 product id even if og:image is missing", () => {
  const root = makeDoc({
    href: FLUTTER_PAGE,
    idProduct: "890177",
    images: [
      { src: NEIGHBOR, href: CUTIEFLY_PAGE },
      { src: MAIN, inMain: true },
    ],
  });
  assert.equal(pickListingImage(root, FLUTTER_PAGE).listingSrc, MAIN);
  assert.equal(pickListingImage(root, FLUTTER_PAGE).listingHow, "idProduct-img");
});

test("does not accept a neighbor thumb when there is no product image yet", () => {
  const root = makeDoc({
    href: FLUTTER_PAGE,
    images: [{ src: NEIGHBOR, href: CUTIEFLY_PAGE }],
  });
  const picked = pickListingImage(root, FLUTTER_PAGE);
  assert.equal(picked.listingSrc, "");
  assert.equal(picked.hasListingImage, false);
});
