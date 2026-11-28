import { expect, test } from "@playwright/test";
import { api, askAssistant, setup, value } from "./helpers";

test("a later goal protection prevents applying an earlier suggestion", async ({ page }) => {
  await setup(page, { condition: "adaptive", aiMode: "fallback" });
  await askAssistant(page, "Help me get smoother FPS and lower input lag.");
  await page.locator(".msg-assistant").last().getByRole("button", { name: /^Review \d+ changes?$/ }).click();
  const vsync = page.getByRole("checkbox", { name: "Include VSync in the change set" });
  await expect(vsync).toBeEnabled();

  await askAssistant(page, "Keep VSync unchanged.");
  await expect(page.locator(".msg-assistant")).toHaveCount(2);
  await expect(vsync).toBeDisabled();
  await expect(vsync).not.toBeChecked();
  await page.getByRole("button", { name: /^Apply selected changes/ }).click();
  await expect(page.locator(".toast").last()).toContainText("Applied");
  expect(await value(page, "valorant", "val.video.vsync")).toBe("on");
  await api(page, "/api/games/valorant/settings/val.video.vsync", "PUT", { value: "off" });
  expect(await value(page, "valorant", "val.video.vsync")).toBe("off");
});
