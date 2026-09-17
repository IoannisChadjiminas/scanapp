import assert from "node:assert/strict";
import test from "node:test";

import { parseAmount } from "../lib/parse.js";
import { classifyPage } from "../lib/extract.js";

test("parses supported Cardmarket amounts and rejects invalid ones", () => {
  assert.equal(parseAmount("1,50 €"), 1.5);
  assert.equal(parseAmount("12.50"), 12.5);
  assert.equal(parseAmount("1.234,56"), 1234.56);
  assert.equal(parseAmount("1,234.56"), 1234.56);
  assert.equal(parseAmount("free"), null);
  assert.equal(parseAmount("0,00"), null);
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
