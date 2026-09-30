import { expect, test } from "@playwright/test";

test("without WebMCP feature flag the dashboard reports no WebMCP tools", async ({ page }) => {
  await page.goto("/smart-kettle/out/smart-kettle/");
  await expect(page.locator("#diagnostics")).toContainText('"webmcp": false');
  const available = await page.evaluate(() => Boolean(document.modelContext));
  expect(available).toBe(false);
});
