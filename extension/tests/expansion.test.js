import assert from "node:assert/strict";
import test from "node:test";

import { collectExpansionSnapshot, nextExpansionPage } from "../lib/expansion.js";

const PAGE = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt";
const GENGAR =
  "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102";

function fakeRoot(anchors) {
  const nodes = anchors.map((item) => ({
    href: item.href,
    textContent: item.text || "",
    getAttribute(name) {
      if (name === "href") {
        return item.href;
      }
      if (name === "rel") {
        return item.rel || "";
      }
      return "";
    },
  }));
  return {
    querySelectorAll() {
      return nodes;
    },
  };
}

test("collects product rows and ignores the set-list URL", () => {
  const snap = collectExpansionSnapshot(
    fakeRoot([
      { href: PAGE, text: "Tag Bolt" },
      { href: GENGAR, text: "Gengar & Mimikyu GX" },
      { href: `${PAGE}?site=2`, rel: "next", text: "Next" },
    ]),
    PAGE,
  );
  assert.equal(snap.products.length, 1);
  assert.equal(snap.products[0].url, GENGAR);
  assert.equal(snap.nextPage, `${PAGE}?site=2`);
});

test("follows site pagination when rel=next is missing", () => {
  assert.equal(
    nextExpansionPage([{ href: `${PAGE}?site=2`, text: "2" }], PAGE),
    `${PAGE}?site=2`,
  );
  assert.equal(nextExpansionPage([{ href: `${PAGE}?site=1`, text: "1" }], PAGE), null);
});
