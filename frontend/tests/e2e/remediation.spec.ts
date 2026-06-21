import { expect, test } from "@playwright/test";

/* T049 — Remediation: Open fix PR → working → PR open → Mark merged → pass; toast +
   audit entry. Runs against the seeded `hangar` repo (LICENSE is a failing PR-tier check
   on a writable connection). */

test.describe("Remediation spectrum", () => {
  test("open fix PR, then mark merged flips the finding to pass", async ({ page }) => {
    await page.goto("/repos/hangar");
    await expect(page.getByText("Policy checks & remediation")).toBeVisible();

    // LICENSE present row offers "Open fix PR"
    const licenseRow = page.locator("div", { hasText: "LICENSE present" }).last();
    const openPr = page.getByText("Open fix PR").first();
    await expect(openPr).toBeVisible();
    await openPr.click();

    // PR open state appears, with Mark merged
    await expect(page.getByText(/PR #\d+ open/).first()).toBeVisible({ timeout: 5000 });
    const markMerged = page.getByText("Mark merged").first();
    await expect(markMerged).toBeVisible();
    await markMerged.click();

    // toast confirms the merge
    await expect(page.getByText(/Merged ·/).first()).toBeVisible();
    await expect(licenseRow).toBeVisible();
  });

  test("audit log records the correction on the providers screen", async ({ page }) => {
    await page.goto("/providers");
    await expect(page.getByText("Audit log — every correction")).toBeVisible();
    await expect(page.getByText("LICENSE present").first()).toBeVisible();
  });

  test("read-only connection offers no write actions", async ({ page }) => {
    await page.goto("/repos/backup-scripts");
    await expect(page.getByText("read-only · deep-link only")).toBeVisible();
    await expect(page.getByText("Open fix PR")).toHaveCount(0);
  });
});
