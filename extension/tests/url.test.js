import assert from "node:assert/strict";
import test from "node:test";

import {
  classifyUrl,
  finalUrlAllowed,
  listingFilters,
  productIdentity,
} from "../lib/url.js";

const GENGAR =
  "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102";

test("classifies product, search, login, and catalogue links", () => {
  assert.equal(classifyUrl(GENGAR), "product");
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
