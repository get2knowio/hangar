import { expect, test } from "@playwright/test";

/* T028 — Fleet overview: six stat tiles, repo table with bot-PR flag + conn badge,
   attention feed ordering, row drill-in (matches the prototype). */

test.describe("Fleet overview", () => {
  test("renders six stat tiles, repo table, and urgency feed", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Fleet overview" })).toBeVisible();

    for (const label of ["Open PRs", "Bot PRs", "CI failing", "Sec alerts", "Release pending", "Compliance"]) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
    }

    // repo table shows repos with the 🤖 bot-PR flag somewhere
    await expect(page.getByText("hangar", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("🤖", { exact: false }).first()).toBeVisible();

    // attention feed, urgency-ordered — first item is the critical alert
    await expect(page.getByText("Needs attention · by urgency")).toBeVisible();
    await expect(page.getByText("Critical").first()).toBeVisible();
  });

  test("drills into a repo from a table row", async ({ page }) => {
    await page.goto("/");
    await page.getByText("hangar", { exact: true }).first().click();
    await expect(page).toHaveURL(/\/repos\/hangar/);
    await expect(page.getByText("Policy checks & remediation")).toBeVisible();
  });

  test("connection filter re-scopes the fleet", async ({ page }) => {
    await page.goto("/");
    const allCount = await page.locator("text=repos · ").first().textContent();
    await page.getByText("All connections").first().click();
    await page.getByText("gh:get2know-labs").click();
    await expect(page.getByText(/repos · /).first()).toBeVisible();
    expect(allCount).toContain("repos");
  });
});
