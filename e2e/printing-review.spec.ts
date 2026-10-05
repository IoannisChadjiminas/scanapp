import { expect, test } from "@playwright/test";

test("printing and finish are separate explicit choices", async ({ page }) => {
  const prefix = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Scarlet-Violet/";
  const normal = `${prefix}Fuecoco-V1-SV036`;
  const holo = `${prefix}Fuecoco-V2-SV036`;
  const card = { id: "en:sv01-036", name: "Fuecoco", set_id: "sv01",
    set_name: "Scarlet & Violet", collector_number: "036", language: "en",
    has_image: false, image_url: null, variants: {}, cardmarket_url: normal,
    cardmarket_variants: [{ url: normal, label: "Normal", card_id: "en:sv01-036" },
      { url: holo, label: "Holo", card_id: "en:sv01-036" }] };
  const top = { ...card, card_id: card.id, image_url: "", visual_score: .8,
    combined_score: .8, ocr_consistent: null };
  const review = { reason: "printing_not_proven", candidate_group_id: "test",
    grouping_basis: "reference_similarity_or_near_tied_retrieval", reference_coverage_complete: false,
    plausible_printings: [{ ...top, card_id: "en:promo-001", set_name: "Promo", collector_number: "001" }, top],
    guidance: "Include the full card or choose your printing." };
  let feedback: Record<string, unknown> | null = null;
  let priceReads = 0;
  let jobs = 0;
  let cardReads = 0;
  let detailFails = true;
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body });
    if (path === "/api/v1/health") return json({ status: "ready", ready: true, snapshot: "test", coverage: { cards: 2, indexed: 2, missing_images: 0 } });
    if (path === "/api/v1/session/results") return json({ session_id: "test", coverage: null, results: feedback ? [{
      scan_id: "crop", created_at: "2026-10-01T00:00:00Z", status: "printing_ambiguous",
      suggestions: [top], printing_review: review, confirmed_card_id: card.id,
      chosen_cardmarket_url: holo, rejected: false, timings_ms: {},
    }] : [] });
    if (path === "/api/v1/scans") return json({ id: "crop", status: "printing_ambiguous",
      suggestions: [top], printing_review: review, message: review.guidance,
      ocr: { lines: [], failed: false }, coverage: {}, timings_ms: {}, versions: {} });
    if (path === "/api/v1/cards/en:sv01-036" || path === "/api/v1/cards/en%3Asv01-036") {
      cardReads++;
      return detailFails ? json({ detail: "Temporary metadata error" }, 503) : json(card);
    }
    if (path === "/api/v1/scans/crop/feedback") {
      feedback = route.request().postDataJSON();
      return json({ ok: true });
    }
    if (path === "/api/v1/cardmarket/prices") { priceReads++; return json({ url: holo, prices: [], status: "done" }); }
    if (path === "/api/v1/cardmarket/prices/events") return route.fulfill({ contentType: "text/event-stream", body: "" });
    if (path === "/api/v1/cardmarket/jobs") { jobs++; return json({ id: "job", url: holo, card_id: card.id }); }
    throw new Error(`Unexpected API request: ${path}`);
  });
  await page.goto("/");
  // File-input events must not race hydration of this client component.
  await expect(page.getByText(/Indexed 2 of 2 cards/)).toBeVisible();
  const png = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 500; canvas.height = 700;
    canvas.getContext("2d")!.fillRect(0, 0, 500, 700);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await page.locator("#photo-upload").setInputFiles({ name: "test.png", mimeType: "image/png", buffer: Buffer.from(png, "base64") });
  await page.getByRole("button", { name: "Scan crop", exact: true }).click();
  const confirm = page.getByRole("button", { name: "This is the card", exact: true });
  await expect(page.getByText("Printing needs review", { exact: true })).toBeVisible();
  await expect(confirm).toBeDisabled();
  await expect(page.getByRole("button", { name: "Holo", exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Open on Cardmarket" })).toHaveCount(0);
  expect(priceReads).toBe(0); expect(jobs).toBe(0);
  const printing = page.getByRole("button", { name: "Scarlet & Violet · #036 · English", exact: true });
  await printing.click();
  await expect(page.getByRole("alert").filter({ hasText: "Temporary metadata error" })).toBeVisible();
  await expect(confirm).toBeDisabled();
  expect(priceReads).toBe(0); expect(jobs).toBe(0);
  detailFails = false;
  await printing.click();
  await expect(page.getByRole("button", { name: "Holo", exact: true })).toBeVisible();
  await expect(confirm).toBeDisabled();
  expect(cardReads).toBe(2); expect(priceReads).toBe(0);
  await page.getByRole("button", { name: "Holo", exact: true }).click();
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect.poll(() => feedback).toEqual({ action: "confirm", card_id: card.id, cardmarket_url: holo, printing_selected: true });
  await page.getByRole("tab", { name: "Session", exact: true }).click();
  await expect(page.getByRole("link", { name: "Cardmarket", exact: true }).filter({ visible: true })).toHaveAttribute("href", holo);
});
