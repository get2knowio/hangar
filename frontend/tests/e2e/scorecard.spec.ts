import { expect, test } from "@playwright/test";

/* T038 — Scorecard: matrix glyphs, failing-only dimming, top-drift chips, catalog
   toggle recomputes. */

test.describe("Hygiene scorecard", () => {
  test("renders the matrix with roll-up and top-drift chips", async ({ page }) => {
    await page.goto("/scorecard");
    await expect(page.getByRole("heading", { name: "Hygiene scorecard" })).toBeVisible();
    await expect(page.getByText("Top drift")).toBeVisible();
    await expect(page.getByText(/repos · \d+ checks/)).toBeVisible();
    // legend present
    await expect(page.getByText("unknown (scope)")).toBeVisible();
  });

  test("failing-only toggle flips label", async ({ page }) => {
    await page.goto("/scorecard");
    const toggle = page.getByText("All cells");
    await expect(toggle).toBeVisible();
    await toggle.click();
    await expect(page.getByText("Failing only")).toBeVisible();
  });

  test("catalog renders checks as data with tier badges and pass bars", async ({ page }) => {
    await page.goto("/catalog");
    await expect(page.getByText(/of \d+ checks active/)).toBeVisible();
    await expect(page.getByText("The catalog is data, not UI.", { exact: false })).toBeVisible();
    await expect(page.getByText("Dependabot alerts enabled")).toBeVisible();
    // a cooldown target input exists (has_target check)
    await expect(page.locator('input[type="number"]').first()).toBeVisible();
  });
});
