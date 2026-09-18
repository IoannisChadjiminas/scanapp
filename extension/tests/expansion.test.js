import assert from "node:assert/strict";
import test from "node:test";

import { collectExpansionSnapshot, collectExpansionTargets, nextExpansionPage } from "../lib/expansion.js";

const PAGE = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt";
const GENGAR =
  "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102";

function fakeRoot(anchors) {
  const nodes = anchors.map((item) => ({
    href: item.href,
    value: item.value,
    textContent: item.text || "",
    getAttribute(name) {
      if (name === "href") {
        return item.href;
      }
      if (name === "rel") {
        return item.rel || "";
      }
      if (name === "value" || name === "data-value") {
        return item.value || "";
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

test("marks a Cloudflare interstitial as a challenge", () => {
  const snap = collectExpansionSnapshot(fakeRoot([]), PAGE, "Just a moment...");
  assert.equal(snap.challenge, true);
  assert.equal(snap.products.length, 0);
});

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

test("reads expansions from the idExpansion select only", () => {
  const page = "https://www.cardmarket.com/en/Pokemon/Products/Singles";
  const options = [
    { value: "-1", textContent: "All" },
    { value: "2770", textContent: "151" },
    { value: "1234", textContent: "Tag Bolt" },
  ];
  const select = {
    name: "idExpansion",
    id: "idExpansion",
    options,
    getAttribute(name) {
      return name === "name" || name === "id" ? "idExpansion" : "";
    },
  };
  const root = {
    querySelectorAll(sel) {
      if (String(sel) === "select") {
        return [select];
      }
      return [];
    },
  };
  const targets = collectExpansionTargets(root, page);
  assert.deepEqual(
    targets.map((item) => [item.id, item.url]),
    [
      ["2770", "https://www.cardmarket.com/en/Pokemon/Products/Singles?idExpansion=2770"],
      ["1234", "https://www.cardmarket.com/en/Pokemon/Products/Singles?idExpansion=1234"],
    ],
  );
});
