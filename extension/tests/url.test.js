import assert from "node:assert/strict";
import test from "node:test";

import {
  classifyUrl,
  finalUrlAllowed,
  identitiesCompatible,
  listingFilters,
  productIdentity,
} from "../lib/url.js";

const GENGAR =
  "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102";

test("classifies product, search, login, catalogue, and set-list links", () => {
  assert.equal(classifyUrl(GENGAR), "product");
  assert.equal(
    classifyUrl("https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt"),
    "expansion",
  );
  assert.equal(
    classifyUrl("https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt?site=2"),
    "expansion",
  );
  assert.equal(classifyUrl("https://www.cardmarket.com/en/Pokemon/Products/Singles"), "singles-index");
  assert.equal(
    classifyUrl("https://www.cardmarket.com/en/Pokemon/Products/Singles?idExpansion=2770"),
    "expansion",
  );
  assert.equal(classifyUrl("https://prices.pokemontcg.io/cardmarket/base1-4"), "pokemontcg");
  assert.equal(classifyUrl("https://www.cardmarket.com/en/Pokemon/Products/Search?searchString=x"), "search");
  assert.equal(classifyUrl("https://www.cardmarket.com/en/Login"), "login");
  assert.equal(classifyUrl("http://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102"), "invalid");
});

test("keeps listing filters out of the identity", () => {
  assert.deepEqual(listingFilters(`${GENGAR}?minCondition=NM&utm_source=x`), {
    minCondition: "NM",
  });
  assert.equal(productIdentity(GENGAR), "singles:sm9102");
  assert.equal(
    classifyUrl(
      "https://www.cardmarket.com/en/Pokemon/Products/Singles/VMAX-Climax/Blaziken-VMAX-V2-s8b217",
    ),
    "product",
  );
});

test("redirect from pokemontcg is allowed only onto a product page", () => {
  assert.equal(
    finalUrlAllowed("https://prices.pokemontcg.io/cardmarket/base1-4", GENGAR),
    true,
  );
  assert.equal(
    finalUrlAllowed(
      GENGAR,
      "https://www.cardmarket.com/en/Pokemon/Products/Singles/Pokemon-Trading-Card-Game-Classic-Charizard-Ho-Oh-ex-Deck/Pikachu-CLC008",
    ),
    false,
  );
});

test("missing identity does not match another product", () => {
  assert.equal(identitiesCompatible("", "singles:clc008"), false);
  assert.equal(identitiesCompatible(null, "path:tag-bolt/gengar"), false);
  assert.equal(identitiesCompatible("singles:sm9102", "singles:clc008"), false);
  assert.equal(identitiesCompatible("singles:sm9102", "singles:sm9102"), true);
});
