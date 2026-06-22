import { expect, test } from "@playwright/test";

/* T082 — prototype-flow fidelity across the five screens (quickstart B–F, H), incl. the
   theme toggle (light/dark token swap). */

test.describe("UI fidelity", () => {
  test("all five screens are reachable from the sidebar", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Fleet overview" })).toBeVisible();
    await page.getByText("Scorecard", { exact: true }).click();
    await expect(page.getByRole("heading", { name: "Hygiene scorecard" })).toBeVisible();
    await page.getByText("Catalog & policy", { exact: true }).click();
    await expect(page.getByRole("heading", { name: "Check catalog & policy" })).toBeVisible();
    await page.getByText("Providers", { exact: true }).click();
    await expect(page.getByRole("heading", { name: "Providers & access" })).toBeVisible();
  });

  test("theme toggle swaps light/dark tokens", async ({ page }) => {
    await page.goto("/");
    const html = page.locator("html");
    await expect(html).toHaveAttribute("data-theme", "light");
    await page.getByText("Dark", { exact: false }).first().click();
    await expect(html).toHaveAttribute("data-theme", "dark");
  });

  test("access footer shows the forward-auth posture", async ({ page }) => {
    await page.goto("/providers");
    await expect(page.getByText(/HANGAR_FORWARD_AUTH=/)).toBeVisible();
    await expect(page.getByText("Behind Traefik", { exact: true })).toBeVisible();
  });
});
