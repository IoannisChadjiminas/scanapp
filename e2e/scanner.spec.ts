import { expect, test } from "@playwright/test";

test("scanner shell is keyboard reachable", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /identify an english pokémon card/i })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Scanner" })).toBeVisible();
  await page.getByRole("tab", { name: "Scanner" }).focus();
  await expect(page.getByRole("tab", { name: "Scanner" })).toBeFocused();
  await page.getByRole("tab", { name: "Session" }).click();
  await expect(page.getByText(/no scans in this session/i)).toBeVisible();
  await page.getByRole("tab", { name: "Scanner" }).click();
  await expect(page.getByRole("button", { name: /open camera/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /upload photograph/i })).toBeVisible();
});
